from fastapi import APIRouter, HTTPException, Request

from osii.domain.artifacts.extraction_variants import (
    list_extraction_variants,
    promote_extraction_variant,
)
from osii.domain.catalog_db import upsert_document


router = APIRouter(prefix="/api/objects", tags=["extraction-variants"])


@router.get("/{file_id}/extractions")
def get_extractions(request: Request, file_id: str):
    result = list_extraction_variants(request.app.state.osii_root.resolve(), file_id)
    if result is None:
        raise HTTPException(status_code=404, detail="object not found")
    return result


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
