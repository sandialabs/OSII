"""Explicit, bounded plans over read-only mounted sources; PostgreSQL owns state."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from osii.server.sources import resolve_directory

MAX_FILES = 5000


def source_file(root: Path, relative: str) -> Path:
    value = Path(relative)
    if value.is_absolute() or not value.parts or any(p.startswith('.') for p in value.parts):
        raise ValueError("Choose visible files within the mounted source root")
    root = root.resolve()
    target = root / value
    # Do not follow even an internal symlink: the reviewed source must be stable.
    current = root
    for part in value.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Symbolic links cannot be staged")
    if not target.resolve().is_relative_to(root) or not target.is_file():
        raise ValueError("Source file is unavailable or outside the mounted root")
    return target


def configuration_stamp(store, settings) -> str:
    from osii.server.model_connections import ModelConnections
    endpoints = {name: (endpoint.base_url, endpoint.api_key, endpoint.model)
                 for name, endpoint in ModelConnections(store, settings).endpoints().items() if name in {"embedding", "chat"}}
    # Only a digest is persisted in plans; credentials never enter job payloads/logs.
    return hashlib.sha256(json.dumps([store.configuration().get("embedding_model", ""), store.configuration().get("chat_model", ""), endpoints,
                                    settings.extractor_url, settings.ocr_url,
                                    store.setting("processor_endpoints", {"urls": list(settings.processor_urls)})],
                                    sort_keys=True).encode()).hexdigest()


def plan(store, settings, paths: list[str], *, operation: str, embed: bool, synthesizer_name: str | None = None, enricher_name: str | None = None,
         synthesizer_config: dict | None = None, enricher_config: dict | None = None, expert_context: str = "", extractor_name: str | None = None, extractor_config: dict | None = None,
         extraction_policy: str = "make_primary") -> dict:
    from osii.server.processors import catalog, resolve, bounded_config
    if operation == "process" and not any((embed, synthesizer_name, enricher_name)):
        raise ValueError("Select synthesis, enrichment, or embeddings when processing existing text")
    selections = catalog(store, settings) if synthesizer_name or enricher_name or extractor_name else []
    extractor = resolve(selections, extractor_name, 'extractor')
    extract_config = bounded_config(extractor_config or {}, extractor)
    if extraction_policy == 'save_variant' and (operation not in {'extract','reprocess'} or embed or synthesizer_name or enricher_name):
        raise ValueError('Save another extraction version must run extraction alone, without downstream steps')
    synthesizer = resolve(selections, synthesizer_name, 'synthesizer')
    enricher = resolve(selections, enricher_name, 'enricher')
    synth_config = bounded_config(synthesizer_config or {}, synthesizer)
    enrich_config = bounded_config(enricher_config or {}, enricher)
    stamp = configuration_stamp(store, settings)
    root = settings.source_root.resolve()
    selected = set()
    for relative in paths:
        value = Path(relative)
        if value.is_absolute() or any(part.startswith('.') and part != '.' for part in value.parts):
            raise ValueError("Choose visible paths within the mounted source root")
        current = root
        for part in value.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("Symbolic links cannot be staged")
        candidate = root / relative
        if candidate.is_dir():
            directory = resolve_directory(root, relative)
            for base, dirs, files in os.walk(directory, followlinks=False):
                dirs[:] = sorted(d for d in dirs if not d.startswith('.') and not (Path(base)/d).is_symlink())
                for name in sorted(files):
                    if name.startswith('.'):
                        continue
                    target = Path(base)/name
                    if target.is_symlink():
                        continue
                    selected.add(target.relative_to(root).as_posix())
                    if len(selected) > MAX_FILES:
                        raise ValueError("Select a smaller batch (at most 5,000 files per plan)")
        else:
            selected.add(source_file(root, relative).relative_to(root).as_posix())
        if len(selected) > MAX_FILES:
            raise ValueError("Select a smaller batch (at most 5,000 files per plan)")
    if not selected:
        raise ValueError("No visible files match this selection")
    configuration = store.configuration()
    if embed and not configuration.get('embedding_model'):
        raise ValueError("Choose an embedding model in Models, or use text-only processing")
    docs = store.indexed_paths()
    lengths = store.document_text_lengths()
    from osii.processors.synthesis import synthesis_call_estimate
    items = []
    for relative in sorted(selected):
        target = source_file(root, relative)
        stat = target.stat()
        if stat.st_size > 50*1024*1024:
            raise ValueError(f"File exceeds the 50 MiB processing limit: {relative}")
        if extraction_policy == 'save_variant' and relative not in docs:
            raise ValueError('The first usable extraction must become primary before saving other versions')
        if operation in {'embed', 'process'} and relative not in docs:
            raise ValueError(f"Extract text before embedding: {relative}")
        items.append({'display': relative, 'path': relative, 'size_bytes': stat.st_size,
                      'mtime_ns': stat.st_mtime_ns, 'status': 'pending', 'indexed': relative in docs,
                      'synthesis_calls_estimate': synthesis_call_estimate(lengths[relative], synth_config.get('window_chars',100000), extract_metadata=synth_config.get('extract_metadata',True)) if synthesizer_name == 'openai.synthesizer' and relative in lengths else None})
    if stamp != configuration_stamp(store, settings):
        raise ValueError("Model settings changed during preview. Preview the files again.")
    return {'synthesis_calls_estimate': sum(item['synthesis_calls_estimate'] or 0 for item in items), 'version': 1, 'workflow': 'library' if operation != 'missing' else 'intake',
            'operation': operation, 'embed': embed, 'embedding_model': configuration.get('embedding_model', '') if embed else '',
            'embedding_model_name': configuration.get('embedding_model_name', configuration.get('embedding_model', '')) if embed else '',
            'extractor': extractor, 'extractor_config': extract_config, 'extraction_policy': extraction_policy, 'synthesizer': synthesizer, 'enricher': enricher, 'synthesizer_config': synth_config, 'enricher_config': enrich_config,
            'expert_context': expert_context, 'configuration_stamp': stamp, 'items': items}


def public_run(job: dict) -> dict:
    payload = job['payload']
    items = payload.get('items', [])
    completed = sum(item['status'] in {'done', 'error'} for item in items)
    return {**{k: job[k] for k in ('id', 'status', 'created_at', 'logs')}, 'workflow': payload.get('workflow'),
            'total': len(items), 'completed': completed, 'items': [{k:v for k,v in item.items() if k != 'synthesis_calls'} for item in items],
            'expert_context': payload.get('expert_context', ''),
            'operations': {'extraction_policy': payload.get('extraction_policy','make_primary'), 'extract': payload.get('operation') not in {'embed','process'}, 'embed': payload.get('embed', False),
                'synthesize': (payload.get('synthesizer') or {}).get('display_name'),
                'enrich': (payload.get('enricher') or {}).get('display_name')},
            'indexing_status': ('done' if job['status'] == 'done' else 'error' if job['status'] == 'error' else 'running' if job['status'] in {'running','pausing','cancelling'} else 'pending') if payload.get('embed') else None,
            'embedding_model': payload.get('embedding_model_name') or payload.get('embedding_model', ''), 'operation': payload.get('operation', 'legacy'),
            'error': 'Some files need attention. Review the per-file errors and retry.' if job['status'] == 'error' else None}
