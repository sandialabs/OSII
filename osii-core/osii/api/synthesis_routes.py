from fastapi import APIRouter, HTTPException, Request
from osii.domain.tool_actions import submit_tool

router = APIRouter(prefix="/api/synthesis", tags=["synthesis-jobs"])


@router.post("/objects/{file_id}")
def synthesize_object(request: Request, file_id: str, payload: dict):
    name = (payload.get("synthesizer_name") or "").strip()
    if not name:
        return {"error": "synthesizer_name is required"}
    try:
        result = submit_tool(
            request.app.state.osii_root.resolve(),
            {
                "enricher_name": name,
                "scope": {"scope_type": "object", "file_id": file_id},
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
        "file_id": file_id,
        "synthesizer_name": name,
    }
