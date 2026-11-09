"""HTTP adapters for the shared tool catalog and durable queue."""

from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, Request
from osii.domain.tool_actions import submit_tool, tool_catalog

router = APIRouter(prefix="/api/enrichment-jobs", tags=["enrichment-jobs"])


@router.get("/tools")
def tools(request: Request):
    return tool_catalog(request.app.state.osii_root.resolve())


class ToolSubmission(BaseModel):
    enricher_name: str = Field(min_length=1, max_length=200)
    scope: dict
    expert_context: str | None = Field(default=None, max_length=20000)
    enricher_config: dict = Field(default_factory=dict)
    model_bindings: dict[str, str] = Field(default_factory=dict)


@router.post("/run")
def run_enrichment(request: Request, payload: ToolSubmission):
    try:
        return submit_tool(request.app.state.osii_root.resolve(), payload.model_dump())
    except (KeyError, ValueError, RuntimeError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
