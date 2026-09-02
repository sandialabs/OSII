from datetime import datetime, UTC
import os
from pathlib import Path
import sqlite3

from fastapi import APIRouter, HTTPException, Request

from osii.domain.processing.capability_readiness import embedding_readiness
from osii.domain.catalog_db import rebuild_catalog, upsert_document
from osii.domain.scopes.collections import add_documents_to_collection, create_collection
from osii.domain.artifacts.extraction_variants import extract_document_variant
from osii.domain.artifacts.text_representations import get_preferred_text_representation
from osii.domain.processing.intake import (
    add_extractor_plan,
    add_processing_plan,
    add_processed_counts,
    expand_queue_to_files,
    parse_patterns,
)
from osii.domain.processing.jobs import (
    append_log,
    control_run,
    create_run_record,
    enqueue_run,
    get_run,
    list_queue_jobs,
    list_runs,
    queue_status_for_run,
    recover_stale_queue_jobs,
    save_run,
    worker_status,
)
from osii.domain.processing.manifests import save_manifest
from osii.domain.storage.root_descriptor import write_collection_synthesis, write_collection_toml
from osii.domain.storage.folders import folder_stats, get_or_create_folder_id, write_folder_manifest
from osii.domain.storage.synth import write_folder_synth_text
from osii.domain.storage.ids import compute_file_id
from osii.domain.storage.store import ensure_osii_store_layout
from osii.domain.processing.pathing import display_rel, path_within
from osii.domain.processor_settings import merged_processor_settings
from osii.domain.processing.extractor_selection import extractor_routes_path
from osii.extraction.dispatcher import dispatch_extract
from osii.enrichment.registry import resolve_enricher
from osii.indexing.chunking import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_CHUNKING_METHOD,
    validate_chunking_settings,
)
from osii.synthesis.file.firstn import FirstNSynthesizer
from osii.synthesis.file.recursive import RecursiveSynthesizer

router = APIRouter(prefix="/api", tags=["runs"])


def _finish_item_timing(item: dict, started: datetime) -> None:
    finished = datetime.now(UTC)
    item["finished_at"] = finished.isoformat()
    item["duration_seconds"] = round(max(0.0, (finished - started).total_seconds()), 3)


def _honor_run_control(run_id: str) -> bool:
    """Stop safely between files when the API requested pause or cancellation."""
    run = get_run(run_id)
    if run is None:
        return True
    queue_status = queue_status_for_run(run_id)
    control_state = (
        "pause_requested" if queue_status == "pause_requested"
        else "cancel_requested" if queue_status == "cancel_requested"
        else run.get("control_state")
    )
    if control_state == "pause_requested":
        run["status"] = "paused"
        run["control_state"] = "paused"
        save_run(run)
        append_log(run_id, "Run paused after the current file completed.")
        return True
    if control_state == "cancel_requested":
        run["status"] = "cancelled"
        run["control_state"] = "cancelled"
        run["finished_at"] = datetime.now(UTC).isoformat()
        for item in run.get("items", []):
            if item.get("status") in {"pending", "running"}:
                item["status"] = "cancelled"
        save_run(run)
        append_log(run_id, "Run cancelled after the current file completed.")
        return True
    return False


def normalize_user_path(raw: str | None) -> Path | None:
    if not raw:
        return None
    cleaned = str(raw).strip().strip('"').strip("'")
    if not cleaned:
        return None
    return Path(cleaned).expanduser()


def safe_resolve_user_path(raw: str | None, fallback: Path) -> Path:
    p = normalize_user_path(raw)
    if p is None:
        return fallback.resolve()
    try:
        return p.resolve()
    except Exception:
        return fallback.resolve()


def load_parser_routes(config_path: Path) -> list[dict]:
    import tomllib

    if not config_path.exists():
        return [{"name": "default-tika", "extractor": "tika", "extensions": ["*"]}]

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    return data.get("routes", [])


def choose_parser(path: Path, routes: list[dict]) -> str:
    return choose_parser_chain(path, routes)[0]


def choose_parser_chain(path: Path, routes: list[dict]) -> list[str]:
    suffix = path.suffix.lower()
    for route in routes:
        exts = route.get("extensions", [])
        if "*" in exts or suffix in [e.lower() for e in exts]:
            chain = [str(route["extractor"])]
            chain.extend(str(item) for item in route.get("fallbacks", []) if item)
            return list(dict.fromkeys(chain))
    return ["tika"]


class FallbackSynthesizer:
    def __init__(self, names: list[str]) -> None:
        self.names = names

    def synthesize(self, **kwargs):
        failures: list[str] = []
        for name in self.names:
            try:
                return _get_one_synthesizer(name).synthesize(**kwargs)
            except Exception as exc:
                failures.append(f"{name}: {exc}")
        raise RuntimeError("All synthesis providers failed: " + "; ".join(failures))


def _get_one_synthesizer(name: str):
    if name == "firstN":
        return FirstNSynthesizer()
    if name == "recursive":
        return RecursiveSynthesizer()
    from osii.processors.remote import RemoteSynthesizer, resolve_remote_processor
    return RemoteSynthesizer(resolve_remote_processor(name, "synthesizer"))


def get_synthesizer(name: str):
    configured = [item.strip() for item in os.getenv("OSII_SYNTHESIZER_FALLBACKS", "").split(",") if item.strip()]
    chain = list(dict.fromkeys([name, *configured]))
    return FallbackSynthesizer(chain)


def relpath_under(root: Path, path: Path) -> str:
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
        return "" if rel == "." else rel
    except Exception:
        return path.name


def build_folder_artifacts(
    resolved_files: list[Path],
    data_volume_root: Path,
    shared_root: Path,
    osii_store: Path,
    root_folder_id: str,
) -> tuple[int, int]:
    folders_to_docs: dict[str, list[Path]] = {}
    folders_to_subfolders: dict[str, set[Path]] = {}
    all_folders: set[Path] = set()

    for file_path in resolved_files:
        parent = file_path.parent.resolve()
        all_folders.add(parent)

        cursor = parent
        while True:
            all_folders.add(cursor)
            if cursor == shared_root.resolve():
                break
            if cursor.parent == cursor:
                break
            cursor = cursor.parent.resolve()

    for folder in all_folders:
        folders_to_docs[str(folder)] = []
        folders_to_subfolders[str(folder)] = set()

    for file_path in resolved_files:
        folders_to_docs[str(file_path.parent.resolve())].append(file_path.resolve())

    for folder in all_folders:
        if folder == shared_root.resolve():
            continue
        parent = folder.parent.resolve()
        if str(parent) in folders_to_subfolders:
            folders_to_subfolders[str(parent)].add(folder)

    folder_id_map: dict[str, str] = {}
    for folder in sorted(all_folders):
        relpath = relpath_under(shared_root, folder)
        if folder == shared_root.resolve():
            folder_id_map[str(folder)] = root_folder_id
        else:
            folder_id_map[str(folder)] = get_or_create_folder_id(osii_store, relpath)

    for folder in sorted(all_folders):
        folder_id = folder_id_map[str(folder)]
        relpath = relpath_under(shared_root, folder)
        path_hint = relpath

        direct_docs = folders_to_docs[str(folder)]
        direct_subfolders = sorted(list(folders_to_subfolders[str(folder)]), key=lambda p: p.name.lower())

        docs_payload = []
        for doc in sorted(direct_docs, key=lambda p: p.name.lower()):
            docs_payload.append(
                {
                    "source_relpath": relpath_under(data_volume_root, doc),
                    "file_id": compute_file_id(doc),
                }
            )

        subfolders_payload = []
        for sub in direct_subfolders:
            subfolders_payload.append(
                {
                    "folder_id": folder_id_map[str(sub)],
                    "path_hint": relpath_under(shared_root, sub),
                }
            )

        stats = folder_stats(direct_docs, direct_subfolders)

        write_folder_manifest(
            osii_store=osii_store,
            folder_id=folder_id,
            path_hint=path_hint,
            docs=docs_payload,
            subfolders=subfolders_payload,
            stats=stats,
            entrypoints={
                "recommended_file_ids": [d["file_id"] for d in docs_payload[:3]]
            } if docs_payload else None,
        )

        folder_label = relpath if relpath else shared_root.name
        write_folder_synth_text(
            osii_store=osii_store,
            folder_id=folder_id,
            folder_label=folder_label,
            direct_doc_count=len(direct_docs),
            direct_subfolder_count=len(direct_subfolders),
        )

    root_direct_docs = folders_to_docs.get(str(shared_root.resolve()), [])
    root_direct_subfolders = list(folders_to_subfolders.get(str(shared_root.resolve()), set()))
    return len(root_direct_docs), len(root_direct_subfolders)


def run_worker(
    run_id: str,
    resolved_files: list[Path],
    queue_items: list[dict],
    include_subfolders: bool,
    include_patterns: list[str],
    exclude_patterns: list[str],
    context: str,
    intake_name: str,
    data_volume_root: Path,
    osii_store: Path,
    shared_root: Path,
    upload_root: Path,
    parser_routes_path: Path,
    shared_root_host_path: str | None,
    synthesizer_name: str | None,
    synthesizer_config: dict | None,
    extractor_overrides: dict[str, str] | None = None,
    workflow: str = "intake",
    run_extraction: bool = True,
    extract_mode: str = "always",
    extraction_policy: str = "make_primary",
    enricher_name: str | None = None,
    enricher_config: dict | None = None,
    collection_id: str | None = None,
) -> None:
    try:
        ensure_osii_store_layout(osii_store)
        parser_routes = load_parser_routes(parser_routes_path)

        run = get_run(run_id)
        if run is None:
            return
        if _honor_run_control(run_id):
            return
        run = get_run(run_id)
        if run is None:
            return

        run["status"] = "running"
        run["control_state"] = "running"
        if not run.get("started_at"):
            run["started_at"] = datetime.now(UTC).isoformat()
        save_run(run)

        append_log(run_id, "Run started.")
        append_log(run_id, f"Resolved {len(resolved_files)} file(s) for processing.")

        root_folder_id = get_or_create_folder_id(osii_store, "")
        collection_name = intake_name or f"collection-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"

        if workflow == "intake":
            collection_path = write_collection_toml(
                osii_store=osii_store,
                collection_name=collection_name,
                root_folder_id=root_folder_id,
                host_path=shared_root_host_path,
                container_path=str(shared_root),
                notes=context or "",
                tool_versions={"pipeline_version": "osii-v1-draft"},
            )
            append_log(run_id, f"Collection descriptor saved: {collection_path.name}")
            manifest_path = save_manifest(
                resolved_files=resolved_files,
                queue_items=queue_items,
                include_subfolders=include_subfolders,
                include_patterns=include_patterns,
                exclude_patterns=exclude_patterns,
                context=context,
                data_volume_root=data_volume_root,
                osii_root=osii_store,
                shared_root=shared_root,
                upload_root=upload_root,
            )
            run = get_run(run_id)
            if run is None:
                return
            run["manifest_name"] = manifest_path.name
            run["manifest_path"] = str(manifest_path)
            save_run(run)
            append_log(run_id, f"Run manifest saved: {manifest_path.name}")

        for index, src in enumerate(resolved_files):
            if _honor_run_control(run_id):
                return
            run = get_run(run_id)
            if run is None:
                return

            if run["items"][index].get("status") in {"done", "partial", "error"}:
                append_log(run_id, f"Resume: kept completed result for {src.name}.")
                continue

            extension = src.suffix.lower() or "(no extension)"
            extractor_chain = (
                [(extractor_overrides or {})[extension]]
                if extension in (extractor_overrides or {})
                else choose_parser_chain(src, parser_routes)
            )
            extractor_name = extractor_chain[0]
            run["items"][index]["status"] = "running"
            run["items"][index]["extractor"] = extractor_name
            run["items"][index]["synthesizer"] = synthesizer_name
            run["items"][index]["enricher"] = enricher_name
            item_started = datetime.now(UTC)
            run["items"][index]["started_at"] = item_started.isoformat()
            run["items"][index]["finished_at"] = None
            run["items"][index]["duration_seconds"] = None
            save_run(run)

            try:
                file_id = compute_file_id(src)
                existing_text = get_preferred_text_representation(osii_store, file_id)
                should_extract = run_extraction and (extract_mode == "reprocess" or existing_text is None)
                extract_result = None
                if should_extract:
                    extraction_failures: list[str] = []
                    for attempt, candidate in enumerate(extractor_chain):
                        extractor_name = candidate
                        run["items"][index]["extractor"] = extractor_name
                        save_run(run)
                        append_log(run_id, f"Extracting {src.name} with '{extractor_name}'")
                        try:
                            extract_result = extract_document_variant(
                                extractor_name=extractor_name,
                                source_path=src,
                                data_volume_root=data_volume_root,
                                osii_root=osii_store,
                                expert_context=context or None,
                                extractor_config=merged_processor_settings(
                                    osii_store,
                                    extractor_name,
                                    {},
                                ),
                                make_primary=extraction_policy == "make_primary",
                                dispatcher=dispatch_extract,
                            )
                            break
                        except Exception as exc:
                            extraction_failures.append(f"{extractor_name}: {exc}")
                            append_log(run_id, f"Extractor '{extractor_name}' failed for {src.name}: {exc}")
                            if attempt + 1 < len(extractor_chain):
                                append_log(run_id, f"Trying fallback extractor '{extractor_chain[attempt + 1]}'.")
                    if extract_result is None:
                        raise RuntimeError("All configured extractors failed: " + "; ".join(extraction_failures))
                    file_id = extract_result["file_id"]
                    upsert_document(osii_store, file_id)
                    append_log(
                        run_id,
                        f"Extraction variant {extract_result['variant_id']} saved"
                        + (" and made primary." if extract_result["made_primary"] else "."),
                    )
                elif run_extraction:
                    append_log(run_id, f"Skipped extraction for {src.name}; a primary extraction already exists.")
                elif existing_text is None:
                    raise RuntimeError("This document has no extraction. Select extraction before downstream processing.")

                run = get_run(run_id)
                if run is None:
                    return

                run["items"][index]["file_id"] = file_id
                run["items"][index]["extraction_variant_id"] = extract_result.get("variant_id") if extract_result else None
                run["items"][index]["extract_error"] = extract_result.get("error") if extract_result else None

                synthesis_result = None
                synthesis_error = None
                enrichment_result = None
                enrichment_error = None

                if synthesizer_name:
                    if should_extract and extraction_policy != "make_primary":
                        raise RuntimeError("Downstream processing requires the new extraction to be made primary.")
                    append_log(run_id, f"Running synthesizer '{synthesizer_name}' for {src.name}")
                    try:
                        synthesizer = get_synthesizer(synthesizer_name)
                        synthesis_result = synthesizer.synthesize(
                            osii_store=osii_store,
                            file_id=file_id,
                            expert_context=context or None,
                            synthesizer_config=synthesizer_config or {},
                        )
                        append_log(run_id, f"synthesis complete: {src.name}")
                    except Exception as exc:
                        synthesis_error = str(exc)
                        append_log(run_id, f"synthesis error: {src.name} -> {exc}")

                if enricher_name:
                    if should_extract and extraction_policy != "make_primary":
                        raise RuntimeError("Downstream processing requires the new extraction to be made primary.")
                    append_log(run_id, f"Running enricher '{enricher_name}' for {src.name}")
                    try:
                        enrichment_result = resolve_enricher(enricher_name).enrich(
                            osii_store=osii_store,
                            scope={"scope_type": "object", "file_id": file_id},
                            expert_context=context or None,
                            enricher_config=enricher_config or {},
                        )
                        append_log(run_id, f"Enrichment complete: {src.name}")
                    except Exception as exc:
                        enrichment_error = str(exc)
                        append_log(run_id, f"Enrichment error: {src.name} -> {exc}")

                run = get_run(run_id)
                if run is None:
                    return

                errors = [item for item in [extract_result.get("error") if extract_result else None, synthesis_error, enrichment_error] if item]
                run["items"][index]["status"] = "partial" if errors else "done"
                run["items"][index]["osii"] = extract_result["osii_rel"] if extract_result else f"objects/{file_id}"
                run["items"][index]["synthesis"] = synthesis_result["synthesis_rel"] if synthesis_result else None
                run["items"][index]["synthesis_provenance"] = synthesis_result["provenance_rel"] if synthesis_result else None
                run["items"][index]["synthesis_error"] = synthesis_error
                run["items"][index]["enrichment"] = enrichment_result.get("result") if enrichment_result else None
                run["items"][index]["enrichment_error"] = enrichment_error
                run["items"][index]["error"] = "; ".join(errors) if errors else None
                _finish_item_timing(run["items"][index], item_started)
                run["completed"] += 1
                save_run(run)

                if collection_id:
                    add_documents_to_collection(osii_store, collection_id, [file_id])
                    append_log(run_id, f"Added {src.name} to logical collection {collection_id}.")

                append_log(run_id, f"Done: {src.name}")

            except Exception as exc:
                run = get_run(run_id)
                if run is None:
                    return

                try:
                    run["items"][index]["file_id"] = compute_file_id(src)
                except Exception:
                    pass

                run["items"][index]["status"] = "error"
                run["items"][index]["error"] = str(exc)
                _finish_item_timing(run["items"][index], item_started)
                run["completed"] += 1
                save_run(run)

                append_log(run_id, f"Error: {src.name} -> {exc}")

        if _honor_run_control(run_id):
            return

        if workflow == "intake":
            top_level_doc_count, top_level_subfolder_count = build_folder_artifacts(
                resolved_files=resolved_files,
                data_volume_root=data_volume_root,
                shared_root=shared_root,
                osii_store=osii_store,
                root_folder_id=root_folder_id,
            )
            append_log(run_id, "Folder manifests and synthesis updated.")
            write_collection_synthesis(
                osii_store=osii_store,
                collection_name=collection_name,
                root_folder_label=shared_root.name,
                total_files=len(resolved_files),
                top_level_doc_count=top_level_doc_count,
                top_level_subfolder_count=top_level_subfolder_count,
                note=context or None,
            )
            append_log(run_id, "Collection synthesis updated.")
        rebuild_catalog(osii_store)

        if _honor_run_control(run_id):
            return

        run = get_run(run_id)
        if run is None:
            return

        run["status"] = "done"
        run["finished_at"] = datetime.now(UTC).isoformat()
        save_run(run)

        append_log(run_id, "Run complete.")

    except Exception as exc:
        run = get_run(run_id)
        if run is not None:
            run["status"] = "error"
            run["error"] = str(exc)
            run["finished_at"] = datetime.now(UTC).isoformat()
            save_run(run)

        append_log(run_id, f"Run failed: {exc}")


@router.post("/runs")
async def start_run(request: Request, payload: dict):
    shared_root = request.app.state.shared_volume_root.resolve()
    upload_root = request.app.state.upload_originals_root.resolve()
    osii_store = request.app.state.osii_root.resolve()
    data_volume_root = shared_root.parent.resolve()

    queue_paths = payload.get("queue_paths", [])
    include_subfolders = bool(payload.get("include_subfolders", True))
    show_hidden = bool(payload.get("show_hidden", False))

    raw_include = payload.get("include_patterns", "")
    raw_exclude = payload.get("exclude_patterns", "")

    include_patterns = parse_patterns("\n".join(raw_include) if isinstance(raw_include, list) else raw_include)
    exclude_patterns = parse_patterns("\n".join(raw_exclude) if isinstance(raw_exclude, list) else raw_exclude)

    max_files = payload.get("max_files")
    max_total_size_mb = payload.get("max_total_size_mb")
    raw_context = payload.get("expert_context")
    if raw_context is None:
        raw_context = payload.get("context", "")
    if not isinstance(raw_context, str):
        raise HTTPException(status_code=422, detail="expert_context must be a string or null")
    context = raw_context.strip()
    if len(context) > 20_000:
        raise HTTPException(status_code=422, detail="expert_context must not exceed 20,000 characters")
    intake_name = payload.get("intake_name", "")
    workflow = str(payload.get("workflow") or "intake").strip().lower()
    if workflow not in {"intake", "library"}:
        raise HTTPException(status_code=422, detail="workflow must be 'intake' or 'library'")
    run_extraction = bool(payload.get("run_extraction", True))
    extract_mode = str(payload.get("extract_mode") or ("missing" if workflow == "intake" else "reprocess")).strip().lower()
    if extract_mode not in {"missing", "reprocess"}:
        raise HTTPException(status_code=422, detail="extract_mode must be 'missing' or 'reprocess'")
    extraction_policy = str(payload.get("extraction_policy") or "make_primary").strip().lower()
    if extraction_policy not in {"make_primary", "save_variant"}:
        raise HTTPException(status_code=422, detail="extraction_policy must be 'make_primary' or 'save_variant'")
    synthesizer_name = payload.get("synthesizer_name") or None
    synthesizer_config = merged_processor_settings(
        osii_store,
        synthesizer_name,
        payload.get("synthesizer_config"),
    )
    enricher_name = payload.get("enricher_name") or None
    enricher_config = merged_processor_settings(
        osii_store,
        enricher_name,
        payload.get("enricher_config"),
    )
    extractor_overrides = {
        str(extension).lower(): str(extractor)
        for extension, extractor in (payload.get("extractor_overrides") or {}).items()
        if extractor
    }
    build_embeddings = bool(payload.get("build_embeddings", False))
    chunking_method = str(payload.get("chunking_method") or DEFAULT_CHUNKING_METHOD)
    chunk_size = int(payload.get("chunk_size", DEFAULT_CHUNK_SIZE))
    chunk_overlap = int(payload.get("chunk_overlap", DEFAULT_CHUNK_OVERLAP))
    try:
        validate_chunking_settings(chunking_method, chunk_size, chunk_overlap)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not any((run_extraction, synthesizer_name, enricher_name, build_embeddings)):
        raise HTTPException(status_code=422, detail="Select at least one processing operation.")
    if extraction_policy == "save_variant" and any((synthesizer_name, enricher_name, build_embeddings)):
        raise HTTPException(
            status_code=409,
            detail="A saved secondary extraction cannot feed downstream steps until it is made primary. Queue extraction alone or choose Make primary.",
        )

    max_files_int = int(max_files) if max_files not in (None, "") else None
    max_total_size = int(float(max_total_size_mb) * 1024 * 1024) if max_total_size_mb not in (None, "") else None

    queue_items = []
    for raw in queue_paths:
        p = safe_resolve_user_path(raw, shared_root)
        if p.exists():
            queue_items.append(
                {
                    "path": str(p),
                    "display": display_rel(p, shared_root, upload_root),
                    "kind": "folder" if p.is_dir() else "file",
                    "source": "shared" if path_within(shared_root, p) else "upload",
                }
            )

    resolved_files, preview = expand_queue_to_files(
        queue_items=queue_items,
        include_subfolders=include_subfolders,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        show_hidden=show_hidden,
        max_files=max_files_int,
        max_total_size=max_total_size,
        shared_root=shared_root,
        upload_root=upload_root,
    )
    add_processed_counts(preview, resolved_files, data_volume_root, osii_store)
    add_extractor_plan(preview, resolved_files, extractor_overrides)
    add_processing_plan(
        preview,
        resolved_files,
        osii_store,
        run_extraction=run_extraction,
        extract_mode=extract_mode,
        synthesize=bool(synthesizer_name),
        embed=build_embeddings,
        enrich=bool(enricher_name),
    )

    if workflow == "library" and not run_extraction:
        resolved_files = [
            path
            for path in resolved_files
            if get_preferred_text_representation(osii_store, compute_file_id(path)) is not None
        ]
    if workflow == "library":
        unique_files: dict[str, Path] = {}
        for path in resolved_files:
            unique_files.setdefault(compute_file_id(path), path)
        resolved_files = list(unique_files.values())
    if not resolved_files:
        raise HTTPException(status_code=409, detail="No eligible documents matched this processing plan.")

    collection: dict | None = None
    collection_name: str | None = None
    collection_description: str | None = None
    collection_request = payload.get("collection")
    if collection_request is not None:
        if workflow != "intake":
            raise HTTPException(status_code=422, detail="A logical collection can be created only from an Intake run.")
        if not isinstance(collection_request, dict):
            raise HTTPException(status_code=422, detail="collection must be an object with a name and optional description")
        collection_name = collection_request.get("name", "")
        collection_description = collection_request.get("description")
        if not isinstance(collection_name, str):
            raise HTTPException(status_code=422, detail="collection.name must be a string")
        if collection_description is not None and not isinstance(collection_description, str):
            raise HTTPException(status_code=422, detail="collection.description must be a string or null")
    if build_embeddings:
        embedding_status = embedding_readiness(osii_store)
        if not embedding_status["available"]:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Search embeddings cannot be queued because no tested embedder "
                    f"is available. {embedding_status['detail']}"
                ),
            )

    if collection_name is not None:
        try:
            collection = create_collection(
                osii_store,
                name=collection_name,
                description=collection_description.strip() if collection_description else None,
                kind="intake",
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="A collection with that name already exists.") from exc

    run = create_run_record(
        resolved_files,
        shared_root,
        upload_root,
        osii_root=osii_store,
    )
    run["workflow"] = workflow
    run["expert_context"] = context or None
    run["collection_id"] = collection["id"] if collection else None
    run["operations"] = {
        "extract": run_extraction,
        "extract_mode": extract_mode,
        "extraction_policy": extraction_policy,
        "synthesize": synthesizer_name,
        "embed": build_embeddings,
        "chunking": {
            "method": chunking_method,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        } if build_embeddings else None,
        "enrich": enricher_name,
    }
    save_run(run)

    parser_routes_path = extractor_routes_path()
    shared_root_host_path = getattr(request.app.state, "shared_volume_host_path", "")

    queue_job = enqueue_run(
        run["id"],
        {
            "resolved_files": [str(path) for path in resolved_files],
            "queue_items": queue_items,
            "include_subfolders": include_subfolders,
            "include_patterns": include_patterns,
            "exclude_patterns": exclude_patterns,
            "context": context,
            "intake_name": intake_name,
            "data_volume_root": str(data_volume_root),
            "osii_store": str(osii_store),
            "shared_root": str(shared_root),
            "upload_root": str(upload_root),
            "parser_routes_path": str(parser_routes_path),
            "shared_root_host_path": shared_root_host_path,
            "synthesizer_name": synthesizer_name,
            "synthesizer_config": synthesizer_config,
            "extractor_overrides": extractor_overrides,
            "workflow": workflow,
            "run_extraction": run_extraction,
            "extract_mode": extract_mode,
            "extraction_policy": extraction_policy,
            "build_embeddings": build_embeddings,
            "embedding_batch_size": int(payload.get("embedding_batch_size", 64)),
            "chunking_method": chunking_method,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "enricher_name": enricher_name,
            "enricher_config": enricher_config,
            "collection_id": collection["id"] if collection else None,
        },
    )
    run["status"] = "queued"
    run["control_state"] = "running"
    run["queue_job_id"] = queue_job["id"]
    save_run(run)

    return {
        "id": run["id"],
        "run_id": run["id"],
        "queue_job_id": queue_job["id"],
        "status": "queued",
        "created_at": run["created_at"],
        "resolved_count": len(resolved_files),
        "preview": preview,
        "collection": collection,
    }


@router.get("/runs")
async def list_run_status(limit: int = 100):
    return {
        "runs": list_runs(limit=limit),
        "queue": list_queue_jobs(limit=limit),
        "worker": worker_status(),
    }


@router.post("/runs/recover")
async def recover_run_queue():
    recovered = recover_stale_queue_jobs()
    return {
        "recovered_run_ids": recovered,
        "recovered_count": len(recovered),
        "worker": worker_status(),
    }


@router.get("/runs/{run_id}")
async def get_run_status(run_id: str):
    job = get_run(run_id)
    if job is None:
        return {"error": f"Run not found: {run_id}"}
    return job


@router.post("/runs/{run_id}/{action}")
async def control_run_status(run_id: str, action: str):
    try:
        return control_run(run_id, action)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/runs/{run_id}/logs")
async def get_run_logs(run_id: str):
    job = get_run(run_id)
    if job is None:
        return {"error": f"Run not found: {run_id}"}
    return {"run_id": run_id, "logs": job["logs"]}
