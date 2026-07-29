import threading
from pathlib import Path

from fastapi import APIRouter, Request

from osii.domain.processing.jobs import create_run_record, get_run, append_log
from osii.enrichment.registry import resolve_enricher

router = APIRouter(prefix="/api/enrichment-jobs", tags=["enrichment-jobs"])


def _run_enrichment_job(
    *,
    run_id: str,
    osii_root: Path,
    scope: dict,
    expert_context: str | None,
    enricher_name: str,
    enricher_config: dict,
) -> None:
    try:
        run = get_run(run_id)
        if run is None:
            return

        run["status"] = "running"
        append_log(run_id, f"Starting enrichment using '{enricher_name}'")

        enricher = resolve_enricher(enricher_name)
        result = enricher.enrich(
            osii_store=osii_root,
            scope=scope,
            expert_context=expert_context,
            enricher_config=enricher_config,
        )

        run = get_run(run_id)
        if run is None:
            return

        run["status"] = "done"
        run["completed"] = 1
        run["items"][0]["status"] = "done"
        run["items"][0]["enrichment"] = result.get("result")
        append_log(run_id, "Enrichment complete.")

    except Exception as exc:
        run = get_run(run_id)
        if run is not None:
            run["status"] = "error"
            run["items"][0]["status"] = "error"
            run["items"][0]["error"] = str(exc)
        append_log(run_id, f"Enrichment failed: {exc}")


@router.post("/run")
async def run_enrichment(request: Request, payload: dict):
    osii_root = request.app.state.osii_root.resolve()

    enricher_name = (payload.get("enricher_name") or "").strip()
    if not enricher_name:
        return {"error": "enricher_name is required"}

    scope = payload.get("scope") or {}
    expert_context = payload.get("expert_context")
    enricher_config = payload.get("enricher_config") or {}

    run = create_run_record([osii_root], osii_root, osii_root, osii_root=osii_root)
    run["items"][0]["display"] = str(scope)

    thread = threading.Thread(
        target=_run_enrichment_job,
        kwargs={
            "run_id": run["id"],
            "osii_root": osii_root,
            "scope": scope,
            "expert_context": expert_context,
            "enricher_name": enricher_name,
            "enricher_config": enricher_config,
        },
        daemon=True,
    )
    thread.start()

    return {
        "run_id": run["id"],
        "status": run["status"],
        "scope": scope,
        "enricher_name": enricher_name,
    }
