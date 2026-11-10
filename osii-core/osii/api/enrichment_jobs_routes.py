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


@router.get("/runs/{run_id}/batches")
def batch_details(run_id: str, request: Request, cursor: int = 0, limit: int = 20):
    from osii.domain.processing.scope_batches_local import details
    from osii.domain.processing.jobs import get_run
    run=get_run(run_id)
    if not run or not run.get('batch_progress'):
        raise HTTPException(404,'Batch run not found')
    try:return details(request.app.state.osii_root.resolve(),run_id,cursor,limit)
    except (ValueError,FileNotFoundError):raise HTTPException(404,'Batch details not found') from None


@router.get("/runs/{run_id}/batches/{batch_id}")
def one_batch(run_id: str, batch_id: str, request: Request):
    from osii.domain.processing.scope_batches_local import batch_result
    from osii.domain.processing.jobs import get_run
    run=get_run(run_id)
    if not run or not run.get('batch_progress'):raise HTTPException(404,'Batch run not found')
    try:return batch_result(request.app.state.osii_root.resolve(),run_id,batch_id)
    except (ValueError,FileNotFoundError):raise HTTPException(404,'Batch result not found') from None


@router.get("/runs/{run_id}/sources")
def run_sources(run_id: str, request: Request, cursor: int = 0, limit: int = 50, only_missing: bool = False):
    from osii.domain.processing.scope_batches_local import source_details
    from osii.domain.processing.jobs import get_run
    run=get_run(run_id)
    if not run or not run.get('batch_progress'):raise HTTPException(404,'Batch run not found')
    try:return source_details(request.app.state.osii_root.resolve(),run_id,cursor,limit,only_missing)
    except (ValueError,FileNotFoundError):raise HTTPException(404,'Source details not found') from None
