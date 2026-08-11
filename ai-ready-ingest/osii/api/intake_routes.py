import fnmatch
import os
import re
import uuid
from pathlib import Path

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
from osii.domain.processing.pathing import display_rel, path_within

router = APIRouter(prefix="/api", tags=["intake"])


def _safe_upload_name(filename: str | None) -> str:
    name = Path(filename or "upload.bin").name
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    return safe or "upload.bin"


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


@router.get("/intake/readiness")
async def intake_readiness(request: Request):
    return intake_capability_readiness(request.app.state.osii_root.resolve())


@router.get("/browse")
async def browse(
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

    current = safe_resolve_user_path(path, shared_root)
    if not path_within(shared_root, current):
        current = shared_root

    entries = []
    try:
        children = sorted(current.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except Exception:
        children = []

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

    return {
        "current_path": str(current),
        "display_path": display_rel(current, shared_root, upload_root),
        "entries": entries,
    }


@router.post("/resolve")
async def resolve_queue(request: Request, payload: dict):
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
    add_processed_counts(preview, resolved_files, shared_root.parent, request.app.state.osii_root)
    add_extractor_plan(preview, resolved_files, extractor_overrides)
    add_processing_plan(
        preview,
        resolved_files,
        request.app.state.osii_root,
        run_extraction=bool(payload.get("run_extraction", True)),
        extract_mode=str(payload.get("extract_mode") or "missing"),
        synthesize=bool(payload.get("synthesizer_name")),
        embed=bool(payload.get("build_embeddings", False)),
        enrich=bool(payload.get("enricher_name")),
    )

    return {
        "queue_items": queue_items,
        "resolved_files": [
            {
                "path": str(p),
                "display": display_rel(p, shared_root, upload_root),
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
