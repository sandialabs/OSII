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
                 for name, endpoint in ModelConnections(store, settings).endpoints().items() if name == "embedding"}
    # Only a digest is persisted in plans; credentials never enter job payloads/logs.
    return hashlib.sha256(json.dumps([store.configuration().get("embedding_model", ""), endpoints, settings.extractor_url, settings.ocr_url],
                                    sort_keys=True).encode()).hexdigest()


def plan(store, settings, paths: list[str], *, operation: str, embed: bool) -> dict:
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
    items = []
    for relative in sorted(selected):
        target = source_file(root, relative)
        stat = target.stat()
        if stat.st_size > 50*1024*1024:
            raise ValueError(f"File exceeds the 50 MiB processing limit: {relative}")
        if operation == 'embed' and relative not in docs:
            raise ValueError(f"Extract text before embedding: {relative}")
        items.append({'display': relative, 'path': relative, 'size_bytes': stat.st_size,
                      'mtime_ns': stat.st_mtime_ns, 'status': 'pending', 'indexed': relative in docs})
    if stamp != configuration_stamp(store, settings):
        raise ValueError("Model settings changed during preview. Preview the files again.")
    return {'version': 1, 'workflow': 'library' if operation != 'missing' else 'intake',
            'operation': operation, 'embed': embed, 'embedding_model': configuration.get('embedding_model', '') if embed else '',
            'embedding_model_name': configuration.get('embedding_model_name', configuration.get('embedding_model', '')) if embed else '',
            'configuration_stamp': stamp, 'items': items}


def public_run(job: dict) -> dict:
    payload = job['payload']
    items = payload.get('items', [])
    completed = sum(item['status'] in {'done', 'error'} for item in items)
    return {**{k: job[k] for k in ('id', 'status', 'created_at', 'logs')}, 'workflow': payload.get('workflow'),
            'total': len(items), 'completed': completed, 'items': items,
            'operations': {'extract': payload.get('operation') != 'embed', 'embed': payload.get('embed', False)},
            'indexing_status': ('done' if job['status'] == 'done' else 'error' if job['status'] == 'error' else 'running' if job['status'] in {'running','pausing','cancelling'} else 'pending') if payload.get('embed') else None,
            'embedding_model': payload.get('embedding_model_name') or payload.get('embedding_model', ''), 'operation': payload.get('operation', 'legacy'),
            'error': 'Some files need attention. Review the per-file errors and retry.' if job['status'] == 'error' else None}
