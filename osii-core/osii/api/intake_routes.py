import fnmatch
import os
import re
import uuid
from pathlib import Path, PureWindowsPath

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile

from osii.domain.processing.intake import (
    add_extractor_plan,
    add_processing_plan,
    add_processed_counts,
    expand_queue_to_files,
    is_source_processed,
    parse_patterns,
    processed_source_relpaths,
)
from osii.domain.processing.capability_readiness import intake_capability_readiness
from osii.domain.processing.reconcile import reconcile_osii_with_source
from osii.domain.processing.reconcile_apply import apply_source_path_reconciliation
from osii.domain.processing.pathing import display_rel, path_within
from osii.domain.processing.source_access import resolve_intake_path, source_access_summary
from osii.domain.catalog_db import rebuild_catalog

router = APIRouter(prefix="/api", tags=["intake"])


@router.get("/intake/defaults")
def default_intake_settings():
    from osii.domain.processing.defaults import configured_intake_defaults
    try:
        return configured_intake_defaults()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.put("/intake/defaults")
def update_intake_defaults(payload: dict):
    from jsonschema import ValidationError
    from osii.domain.processing.defaults import save_intake_defaults
    try:
        return save_intake_defaults(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _safe_upload_name(filename: str | None) -> str:
    name = Path(filename or "upload.bin").name
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    return safe or "upload.bin"


def resolve_requested_path(request: Request, raw: str | None) -> Path:
    try:
        return resolve_intake_path(
            raw,
            request.app.state.shared_volume_root,
            request.app.state.upload_originals_root,
            filesystem_mode=getattr(request.app.state, "filesystem_mode", "local"),
            host_root=getattr(request.app.state, "shared_volume_host_path", ""),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Cannot open this location: {exc}") from exc


@router.get("/intake/readiness")
def intake_readiness(request: Request):
    osii_root = request.app.state.osii_root.resolve()
    payload = intake_capability_readiness(osii_root)
    payload["source"] = source_access_summary(
        request.app.state.shared_volume_root,
        osii_root,
        configured_kind=getattr(request.app.state, "source_kind", "auto"),
    )
    return payload


@router.post("/intake/rescan-sources")
def rescan_sources(request: Request, payload: dict):
    """Find moved originals by content hash and optionally repair their paths."""
    shared_root = request.app.state.shared_volume_root.resolve()
    osii_root = request.app.state.osii_root.resolve()
    data_volume_root = shared_root.parent.resolve()
    # The filesystem is canonical; make sure a stale/empty derived catalog
    # cannot hide objects from the hash comparison.
    rebuild_catalog(osii_root)
    try:
        result = reconcile_osii_with_source(
            osii_root=osii_root,
            data_root=shared_root,
            relpath_root=data_volume_root,
            include_patterns=[],
            exclude_patterns=[],
            show_hidden=bool(payload.get("show_hidden", False)),
        )
    except OSError as exc:
        raise HTTPException(
            status_code=403 if isinstance(exc, PermissionError) else 503,
            detail=(
                f"Cannot finish scanning documents at {shared_root}: {exc}. "
                "Reconnect the shared drive or restore read permission, then retry. "
                "Stored source paths and statuses have not been changed."
            ),
        ) from exc
    if bool(payload.get("apply", False)):
        result["applied"] = apply_source_path_reconciliation(
            reconcile_result=result,
            osii_root=osii_root,
            source_root=shared_root,
            data_volume_root=data_volume_root,
        )
        rebuild_catalog(osii_root)
    return result


@router.get("/browse/roots")
def browse_roots(request: Request):
    """Navigation shortcuts only; never enumerate a mount or directory."""
    if getattr(request.app.state, "filesystem_mode", "local") == "mounted":
        return {
            "items": [
                str(request.app.state.shared_volume_root),
                str(request.app.state.upload_originals_root),
            ]
        }
    roots = [str(Path.home()), str(request.app.state.shared_volume_root)]
    if os.name == "nt":
        import ctypes

        mask = ctypes.windll.kernel32.GetLogicalDrives()
        roots.extend(f"{chr(65 + i)}:/" for i in range(26) if mask & (1 << i))
    else:
        import sys

        roots.extend(["/", "/Volumes" if sys.platform == "darwin" else "/mnt"])
    return {"items": list(dict.fromkeys(roots))}


def _browsers(request):
    from osii.domain.processing.directory_browse import DirectoryBrowsers

    if not hasattr(request.app.state, "directory_browsers"):
        request.app.state.directory_browsers = DirectoryBrowsers()
        request.app.add_event_handler(
            "shutdown", request.app.state.directory_browsers.close_all
        )
    return request.app.state.directory_browsers


@router.get("/browse/page")
async def browse_page(
    request: Request,
    path: str | None = None,
    cursor: str | None = None,
    limit: int = Query(100, ge=1, le=200),
    show_hidden: bool = False,
):
    browsers = _browsers(request)
    try:
        token = cursor or browsers.open(
            path,
            request.app.state.shared_volume_root,
            request.app.state.upload_originals_root,
            getattr(request.app.state, "filesystem_mode", "local"),
            getattr(request.app.state, "shared_volume_host_path", ""),
            show_hidden,
        )
        result = await browsers.page(token, limit, request.is_disconnected)
    except KeyError as exc:
        raise HTTPException(410, str(exc.args[0])) from exc
    except (TimeoutError, InterruptedError) as exc:
        raise HTTPException(503, str(exc)) from exc
    except (ValueError, OSError, EOFError) as exc:
        raise HTTPException(422, str(exc)) from exc
    if "error" in result:
        raise HTTPException(result["status"], result["error"])
    return result


@router.delete("/browse/page/{cursor}")
async def close_browse(request: Request, cursor: str):
    _browsers(request).close(cursor)
    return {"closed": True}

@router.get("/browse")
def browse(
    request: Request,
    path: str | None = Query(default=None),
    include_patterns: str = Query(default=""),
    exclude_patterns: str = Query(default=""),
    show_hidden: bool = Query(default=False),
):
    shared_root = request.app.state.shared_volume_root.resolve()
    upload_root = request.app.state.upload_originals_root.resolve()
    osii_root = request.app.state.osii_root.resolve()
    data_volume_root = shared_root.parent.resolve()

    current = resolve_requested_path(request, path)
    if not current.is_dir():
        raise HTTPException(status_code=422, detail=f"Choose a folder, not a file: {current}")

    entries = []
    try:
        children = sorted(current.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except OSError as exc:
        raise HTTPException(status_code=403, detail=f"OSII cannot read this folder: {current}. {exc}") from exc

    include_list = parse_patterns(include_patterns)
    exclude_list = parse_patterns(exclude_patterns)
    processed_relpaths = processed_source_relpaths(osii_root)

    for child in children:
        if not show_hidden and child.name.startswith("."):
            continue

        try:
            is_dir = child.is_dir()
            is_file = child.is_file()
        except Exception:
            continue

        if is_file:
            if path_within(shared_root, child):
                rel_match = child.relative_to(shared_root).as_posix()
            elif path_within(upload_root, child):
                rel_match = child.relative_to(upload_root).as_posix()
            else:
                rel_match = child.name

            rel_posix = rel_match.replace("\\", "/")

            if include_list and not any(
                fnmatch.fnmatch(rel_posix.lower(), pattern.lower())
                for pattern in include_list
            ):
                continue

            if exclude_list and any(
                fnmatch.fnmatch(rel_posix.lower(), pattern.lower())
                for pattern in exclude_list
            ):
                continue

        try:
            size = child.stat().st_size if is_file else None
        except Exception:
            size = None

        entries.append(
            {
                "name": child.name,
                "display": display_rel(child, shared_root, upload_root),
                "path": str(child),
                "type": "folder" if is_dir else "file",
                "size_bytes": size,
                "processed": (
                    is_file
                    and is_source_processed(
                        child,
                        data_volume_root,
                        processed_relpaths,
                    )
                ),
            }
        )

    filesystem_mode = getattr(request.app.state, "filesystem_mode", "local")
    host_root = getattr(request.app.state, "shared_volume_host_path", "")
    host_path = str(current)
    if host_root and path_within(shared_root, current):
        host = PureWindowsPath(host_root) if PureWindowsPath(host_root).drive else Path(host_root)
        host_path = str(host.joinpath(*current.relative_to(shared_root).parts))
    parent_path = str(current.parent) if current.parent != current else None
    if filesystem_mode == "mounted" and current in (shared_root, upload_root):
        parent_path = None
    return {
        "current_path": str(current),
        "display_path": display_rel(current, shared_root, upload_root),
        "folder_name": current.name or str(current),
        "parent_path": parent_path,
        "filesystem_mode": filesystem_mode,
        "host_path": host_path,
        "entries": entries,
    }


@router.post("/resolve")
def resolve_queue(request: Request, payload: dict):
    if payload.get("inventory_selection_id") is not None:
        from osii.volume.staging import staged_bundle, selection_preview, selection_id
        try:
            return selection_preview(
                staged_bundle(request.app.state.osii_root, selection_id(payload["inventory_selection_id"])),
                payload.get("extractor_overrides"), payload,
            )
        except (ValueError, KeyError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    shared_root = request.app.state.shared_volume_root.resolve()
    upload_root = request.app.state.upload_originals_root.resolve()

    queue_paths = payload.get("queue_paths", [])
    include_subfolders = bool(payload.get("include_subfolders", True))
    show_hidden = bool(payload.get("show_hidden", False))

    raw_include = payload.get("include_patterns", "")
    raw_exclude = payload.get("exclude_patterns", "")
    extractor_overrides = payload.get("extractor_overrides") or {}

    include_patterns = parse_patterns("\n".join(raw_include) if isinstance(raw_include, list) else raw_include)
    exclude_patterns = parse_patterns("\n".join(raw_exclude) if isinstance(raw_exclude, list) else raw_exclude)

    max_files = payload.get("max_files")
    max_total_size_mb = payload.get("max_total_size_mb")

    max_files_int = int(max_files) if max_files not in (None, "") else None
    max_total_size = int(float(max_total_size_mb) * 1024 * 1024) if max_total_size_mb not in (None, "") else None

    queue_items = []
    for raw in queue_paths:
        p = resolve_requested_path(request, raw)
        if p.exists():
            queue_items.append(
                {
                    "path": str(p),
                    "display": display_rel(p, shared_root, upload_root),
                    "kind": "folder" if p.is_dir() else "file",
                    "source": "shared" if path_within(shared_root, p) else "upload",
                }
            )

    try:
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
            excluded_paths=payload.get("excluded_paths", []),
        )
    except OSError as exc:
        raise HTTPException(status_code=503, detail=(
            f"Could not finish listing this folder ({type(exc).__name__}). "
            "Check share access or choose individual files using Browse files."
        )) from exc
    if getattr(request.app.state, "filesystem_mode", "local") == "mounted":
        for file in preview["available_files"]:
            resolve_requested_path(request, file["path"])
    if payload.get("metadata_only") is not True:
        add_processed_counts(preview, resolved_files, shared_root.parent, request.app.state.osii_root)
        add_extractor_plan(preview, resolved_files, extractor_overrides)
        add_processing_plan(
            preview,
            resolved_files,
            request.app.state.osii_root,
            data_volume_root=shared_root.parent,
            run_extraction=bool(payload.get("run_extraction", True)),
            extract_mode=str(payload.get("extract_mode") or "missing"),
            synthesize=bool(payload.get("synthesizer_name")),
            embed=bool(payload.get("build_embeddings", False)),
            enrich=bool(payload.get("enricher_name")),
        )

    displays = {item["path"]: item["display"] for item in preview["available_files"]}
    return {
        "queue_items": queue_items,
        "resolved_files": [
            {
                "path": str(p),
                "display": displays[str(p)],
            }
            for p in resolved_files
        ],
        "preview": preview,
    }


@router.post("/uploads")
async def upload_files(
    request: Request,
    files: list[UploadFile] = File(...),
):
    """Copy one-off files into the upload volume for normal queue processing."""
    upload_root = request.app.state.upload_originals_root.resolve()
    max_bytes = int(os.getenv("OSII_UPLOAD_MAX_BYTES", str(250 * 1024 * 1024)))
    upload_root.mkdir(parents=True, exist_ok=True)
    uploaded = []

    for upload in files:
        safe_name = _safe_upload_name(upload.filename)
        target = upload_root / f"{uuid.uuid4().hex[:12]}-{safe_name}"
        written = 0
        try:
            with target.open("wb") as destination:
                while chunk := await upload.read(1024 * 1024):
                    written += len(chunk)
                    if written > max_bytes:
                        raise HTTPException(
                            status_code=413,
                            detail=f"{safe_name} exceeds the upload limit of {max_bytes} bytes",
                        )
                    destination.write(chunk)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        finally:
            await upload.close()

        uploaded.append(
            {
                "name": safe_name,
                "path": str(target),
                "display": display_rel(target, request.app.state.shared_volume_root, upload_root),
                "size_bytes": written,
                "source": "upload",
            }
        )

    return {"uploads": uploaded}


@router.post("/intake/preflight")
def test_intake_processors(request: Request, payload: dict):
    """Explicit tiny operation tests; no corpus reads or canonical writes."""
    import base64
    import pymupdf
    from osii.processor_sdk import ProcessorClient, ExtractionRequest, DocumentInput, SynthesisRequest, ScopeInput, EnrichmentRequest
    from osii.processor_sdk.diagnostics import failure
    from osii.processors.remote import resolve_remote_processor, _model_context, _revoke_model_context
    from osii.domain.processor_settings import merged_processor_settings
    from osii.domain.processing.capability_readiness import embedding_readiness

    targets = payload.get("processors", [])
    if not isinstance(targets, list) or len(targets) > 8:
        raise HTTPException(422, "Test up to eight selected processors at a time")
    if any(not isinstance(target, dict) or not isinstance(target.get("name"), str)
           or not target["name"] or target.get("kind") not in {"extractor", "synthesizer", "enricher"} for target in targets):
        raise HTTPException(422, "Specify a registered extractor, synthesizer, or enricher")
    results = []
    root = request.app.state.osii_root.resolve()
    for target in targets:
        name, kind = str(target.get("name", "")), target.get("kind")
        if kind not in {"extractor", "synthesizer", "enricher"}:
            raise HTTPException(422, "Unsupported processor test kind")
        context = None
        endpoint = None
        remote_environment = None
        try:
            descriptor = resolve_remote_processor(name, kind)
            endpoint = descriptor["base_url"]
            client = ProcessorClient(endpoint, timeout=120)
            try:
                remote_environment = ProcessorClient(endpoint, timeout=3)._get("/v1/diagnostics")
            except Exception:
                remote_environment = {"detail": "This service did not provide runtime diagnostics"}
            request_id = f"preflight-{uuid.uuid4()}"
            context = _model_context(processor_name=name, descriptor=descriptor, request_id=request_id, osii_root=root)
            config = merged_processor_settings(root, name, {})
            if kind == "extractor":
                extensions = descriptor.get("capabilities", {}).get("file_extensions", [])
                extension = next((ext for ext in (".pdf", ".txt", ".csv", ".png") if ext in extensions or "*" in extensions), None)
                if extension is None:
                    results.append({"processor": name, "endpoint": endpoint, "ok": None, "detail": "No supported synthetic input for this extractor; no operation was tested", "runtime": remote_environment})
                    continue
                media_type = {".pdf": "application/pdf", ".txt": "text/plain", ".csv": "text/csv", ".png": "image/png"}[extension]
                if extension in {".pdf", ".png"}:
                    with pymupdf.open() as pdf:
                        page = pdf.new_page()
                        page.insert_text((72, 72), "OSII endpoint test document.")
                        raw_content = pdf.tobytes() if extension == ".pdf" else page.get_pixmap(dpi=150).tobytes("png")
                    from osii.domain.processing.flows import TEXT_LAYER_SAMPLE, TEXT_LAYER_SAMPLE_PAGE, TEXT_LAYER_SAMPLE_ID
                    requested_sample = payload.get("sample")
                    if requested_sample in {TEXT_LAYER_SAMPLE_ID, "purcell-first-page"}:
                        sample = TEXT_LAYER_SAMPLE if requested_sample == TEXT_LAYER_SAMPLE_ID else Path(__file__).resolve().parents[3] / "scripts/demo-data/purcell.pdf"
                        page_index = TEXT_LAYER_SAMPLE_PAGE if requested_sample == TEXT_LAYER_SAMPLE_ID else 0
                        if not sample.is_file():
                            raise FileNotFoundError(f"Bundled sample PDF is missing: {sample.name}. Restore it from scripts/demo-data.")
                        with pymupdf.open(sample) as original, pymupdf.open() as one_page:
                            if requested_sample == TEXT_LAYER_SAMPLE_ID and not original[page_index].get_text().strip():
                                raise ValueError("Bundled standard sample has no text layer; restore the NIST test PDF")
                            one_page.insert_pdf(original, from_page=page_index, to_page=page_index)
                            raw_content = one_page.tobytes() if extension == ".pdf" else one_page[0].get_pixmap(dpi=150).tobytes("png")
                else:
                    raw_content = b"name,value\nosii,1\n" if extension == ".csv" else b"OSII endpoint test document."
                content = base64.b64encode(raw_content).decode("ascii")
                response = client.extract(ExtractionRequest(request_id=request_id,
                    document=DocumentInput(filename="osii-test" + extension, media_type=media_type, content_base64=content),
                    config=config, model_context=context))
                if not response.segments:
                    raise ValueError("Extractor returned no text for the test document")
            else:
                operation = client.synthesize if kind == "synthesizer" else client.enrich
                model = SynthesisRequest if kind == "synthesizer" else EnrichmentRequest
                operation(model(request_id=request_id,
                    scope=ScopeInput(scope_type="object", scope_id=request_id,
                        documents=[DocumentInput(filename="osii-test.txt", text="OSII endpoint test document.")]),
                    config=config, model_context=context))
            results.append({"processor": name, "endpoint": endpoint, "ok": True, "detail": "Tiny operation passed", "runtime": remote_environment})
        except Exception as exc:
            results.append({"processor": name, "ok": False, "diagnostics": failure(exc, processor=name, phase="preflight", endpoint=endpoint), "runtime": remote_environment})
        finally:
            _revoke_model_context(context)
    if payload.get("embed"):
        result = embedding_readiness(root)
        results.append({"processor": "Selected embedding model", "ok": bool(result.get("available")), "detail": result.get("detail"), "result": result})
    return {"results": results, "tested_at": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat()}


@router.get("/processing-flows")
def list_processing_flows(request: Request):
    from osii.domain.processing.flows import processing_flows
    return {"flows": processing_flows(request.app.state.osii_root.resolve())}


@router.put("/processing-flows/{flow_id}")
def save_processing_flow(request: Request, flow_id: str, payload: dict):
    from osii.configuration import load_tools_config, save_tools_config
    from osii.api.extractor_routes import validate_routes
    from osii.domain.processing.flows import get_flow
    from osii.domain.processing.quick_intake import FLOW_ID
    if flow_id == FLOW_ID:
        raise HTTPException(422, "The standard flow is managed by OSII.")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", flow_id):
        raise HTTPException(422, "Use a short flow ID with letters, numbers, and hyphens")
    name = payload.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 120:
        raise HTTPException(422, "Enter a flow name (up to 120 characters)")
    if not isinstance(payload.get("routes"), list) or not payload["routes"] or len(payload["routes"]) > 32:
        raise HTTPException(422, "Choose 1 to 32 file-type rules")
    errors, warnings = validate_routes({"routes": payload.get("routes")})
    if errors:
        raise HTTPException(422, errors)
    from osii.indexing.chunking import validate_chunking_settings
    from osii.domain.processing.defaults import configured_intake_defaults
    defaults = configured_intake_defaults()
    size, overlap = payload.get("chunk_size", defaults["chunk_size"]), payload.get("chunk_overlap", defaults["chunk_overlap"])
    if type(size) is not int or type(overlap) is not int:
        raise HTTPException(422, "Chunk size and overlap must be integers")
    try:
        validate_chunking_settings("sentence_window", size, overlap)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    for key in ("synthesizer_name", "enricher_name"):
        if key in payload and (not isinstance(payload[key], str) or not payload[key].strip()):
            raise HTTPException(422, "Select a synthesizer and enricher for all processes")
    settings = load_tools_config()
    settings.setdefault("processing_flows", {})[flow_id] = {key: payload[key] for key in (
        "name", "routes", "synthesizer_name", "enricher_name", "chunk_size", "chunk_overlap") if key in payload}
    settings.get("processing_flow_tests", {}).pop(flow_id, None)
    save_tools_config(settings)
    return {"flow": get_flow(request.app.state.osii_root.resolve(), flow_id), "warnings": warnings}


@router.post("/processing-flows/{flow_id}/test")
def test_processing_flow(request: Request, flow_id: str):
    from osii.configuration import load_tools_config, save_tools_config
    from osii.domain.processing.flows import get_flow
    root = request.app.state.osii_root.resolve()
    flow = get_flow(root, flow_id)
    if flow is None:
        raise HTTPException(404, "Processing flow not found")
    results = []
    # Test ordered chains independently; failure of an optional fallback is
    # recorded without invalidating a chain that has a working reader.
    for route in flow["routes"]:
        attempts = []
        for name in [route["extractor"], *route.get("fallbacks", [])]:
            report = test_intake_processors(request, {"processors": [{"name": name, "kind": "extractor"}], "sample": "nist-cloud-definition"})
            attempts.extend(report["results"])
        results.append({"step": "extract", "route": route["name"], "extensions": route["extensions"],
                        "ok": any(item["ok"] is True for item in attempts), "attempts": attempts})
    for kind, name in (("synthesizer", flow["synthesizer_name"]), ("enricher", flow["enricher_name"])):
        report = test_intake_processors(request, {"processors": [{"name": name, "kind": kind}]})
        results.extend({**item, "step": "synthesize" if kind == "synthesizer" else "enrich"} for item in report["results"])
    report = test_intake_processors(request, {"embed": True})
    results.extend({**item, "step": "embed"} for item in report["results"])
    report = {"fingerprint": flow["fingerprint"], "tested_at": report["tested_at"],
              "sample": "NIST cloud-computing definition (PDF page 6) and tiny text samples", "ok": all(item["ok"] is True for item in results), "results": results}
    settings = load_tools_config()
    # Don't stamp a changed configuration with an earlier successful test.
    current = get_flow(root, flow_id)
    if current and current["fingerprint"] == flow["fingerprint"]:
        from osii.configuration import _drop_nulls
        settings.setdefault("processing_flow_tests", {})[flow_id] = _drop_nulls(report)
        save_tools_config(settings)
    return report
