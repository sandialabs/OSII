from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from osii.domain.artifacts.extraction_variants import (
    list_extraction_variants,
    promote_extraction_variant,
)
from osii.domain.catalog_db import upsert_document
from osii.domain.processing.pathing import path_within
from osii.domain.read.docs import get_doc_meta
from osii.domain.storage.ids import compute_file_id


router = APIRouter(prefix="/api/objects", tags=["extraction-variants"])


@router.get("/{file_id}/extractions")
def get_extractions(request: Request, file_id: str):
    result = list_extraction_variants(request.app.state.osii_root.resolve(), file_id)
    if result is None:
        raise HTTPException(status_code=404, detail="object not found")
    return result


def _current_source_path(request: Request, file_id: str) -> Path:
    osii_root = request.app.state.osii_root.resolve()
    meta = get_doc_meta(osii_root, file_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="object not found")

    source_relpath = str((meta.get("file") or {}).get("source_relpath") or "").strip()
    if not source_relpath:
        raise HTTPException(status_code=409, detail="object has no recorded source path")

    shared_root = request.app.state.shared_volume_root.resolve()
    upload_root = request.app.state.upload_originals_root.resolve()
    data_volume_root = shared_root.parent.resolve()
    source_path = (data_volume_root / source_relpath).resolve()
    if not (path_within(shared_root, source_path) or path_within(upload_root, source_path)):
        raise HTTPException(status_code=409, detail="recorded source path is outside the configured source locations")
    if not source_path.is_file():
        raise HTTPException(
            status_code=409,
            detail="original file is not at its recorded path; rescan source paths before re-extracting",
        )
    if compute_file_id(source_path) != file_id:
        raise HTTPException(
            status_code=409,
            detail="original file contents changed; rescan source paths and process it as a changed source",
        )
    return source_path


@router.post("/{file_id}/extractions")
async def queue_extraction(request: Request, file_id: str, payload: dict):
    """Queue one extraction version without scheduling downstream processing."""
    extractor_name = str(payload.get("extractor_name") or "").strip()
    if not extractor_name:
        raise HTTPException(status_code=422, detail="extractor_name is required")
    extraction_policy = str(payload.get("extraction_policy") or "make_primary").strip()
    if extraction_policy not in {"make_primary", "save_variant"}:
        raise HTTPException(
            status_code=422,
            detail="extraction_policy must be 'make_primary' or 'save_variant'",
        )

    source_path = _current_source_path(request, file_id)
    extension = source_path.suffix.lower() or "(no extension)"

    # Reuse the durable run queue so OCR and other slow extractors never block
    # this API request. This route deliberately schedules extraction only.
    from osii.api.runs_routes import start_run

    return await start_run(
        request,
        {
            "queue_paths": [str(source_path)],
            "include_subfolders": False,
            "workflow": "library",
            "run_extraction": True,
            "extract_mode": "reprocess",
            "extraction_policy": extraction_policy,
            "extractor_overrides": {extension: extractor_name},
            "build_embeddings": False,
        },
    )


@router.post("/{file_id}/extractions/{variant_id}/primary")
def make_extraction_primary(request: Request, file_id: str, variant_id: str):
    osii_root = request.app.state.osii_root.resolve()
    try:
        result = promote_extraction_variant(osii_root, file_id, variant_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    upsert_document(osii_root, file_id)
    return result
