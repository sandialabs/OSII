from fastapi import APIRouter, HTTPException, Request
from osii.domain.artifacts.collection_artifacts import (
    get_collection_artifact_summary,
    list_collection_syntheses,
)
from osii.domain.tool_actions import submit_tool
from osii.domain.scopes.collections import get_collection

router = APIRouter(prefix="/api/collections", tags=["collection-synthesis"])


@router.get("/{collection_id}/syntheses")
async def get_collection_syntheses_route(request: Request, collection_id: str):
    osii_root = request.app.state.osii_root.resolve()

    collection = get_collection(osii_root, collection_id)
    if collection is None:
        return {"error": "unknown collection_id"}

    return {
        "collection": collection,
        "syntheses": list_collection_syntheses(osii_root, collection_id),
    }


@router.get("/{collection_id}/artifacts")
async def get_collection_artifacts_route(request: Request, collection_id: str):
    osii_root = request.app.state.osii_root.resolve()

    summary = get_collection_artifact_summary(osii_root, collection_id)
    if summary is None:
        return {"error": "unknown collection_id"}

    return summary


@router.post("/{collection_id}/syntheses")
def run_collection_synthesis_route(request: Request, collection_id: str, payload: dict):
    osii_root = request.app.state.osii_root.resolve()

    collection = get_collection(osii_root, collection_id)
    if collection is None:
        return {"error": "unknown collection_id"}

    synthesizer_name = str(payload.get("synthesizer_name") or "").strip()
    if not synthesizer_name:
        raise HTTPException(
            status_code=422,
            detail="Select a collection synthesizer explicitly.",
        )
    try:
        result = submit_tool(
            osii_root,
            {
                "enricher_name": synthesizer_name,
                "scope": {"scope_type": "collection", "collection_id": collection_id},
                "expert_context": payload.get("expert_context"),
                "enricher_config": payload.get("synthesizer_config") or {},
            },
            method_kind="synthesis",
        )
    except (ValueError, RuntimeError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "run_id": result["run_id"],
        "status": result["status"],
        "collection_id": collection_id,
        "synthesizer_name": synthesizer_name,
    }
