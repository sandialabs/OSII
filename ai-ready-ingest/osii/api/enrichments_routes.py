from fastapi import APIRouter, Request

from osii.domain.artifacts.read_enrichments import (
    get_object_enrichment_payload,
    get_scope_enrichment_payload,
    list_scope_enrichments,
)

router = APIRouter(prefix="/api/enrichments", tags=["enrichments"])


@router.post("/list")
async def list_enrichments_route(request: Request, payload: dict):
    osii_root = request.app.state.osii_root.resolve()
    try:
        items = list_scope_enrichments(osii_root, payload)
    except ValueError as exc:
        return {"error": str(exc)}

    return {
        "scope": payload,
        "enrichments": items,
    }


@router.post("/payload")
async def get_scope_enrichment_route(request: Request, payload: dict):
    osii_root = request.app.state.osii_root.resolve()
    filename = str(payload.get("filename") or "")
    scope = payload.get("scope") or {}
    try:
        data = get_scope_enrichment_payload(osii_root, scope, filename)
    except ValueError as exc:
        return {"error": str(exc)}
    if data is None:
        return {"error": "enrichment not found"}
    return data


@router.get("/objects/{file_id}/{filename}")
async def get_object_enrichment_route(request: Request, file_id: str, filename: str):
    osii_root = request.app.state.osii_root.resolve()
    data = get_object_enrichment_payload(osii_root, file_id, filename)
    if data is None:
        return {"error": "enrichment not found"}
    return data
