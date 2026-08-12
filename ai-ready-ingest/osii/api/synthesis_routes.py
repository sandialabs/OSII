import threading
from pathlib import Path

from fastapi import APIRouter, Request
from osii.api.runs_routes import get_synthesizer
from osii.domain.processing.jobs import append_log, create_run_record, get_run
from osii.domain.processor_settings import merged_processor_settings

router = APIRouter(prefix="/api/synthesis", tags=["synthesis-jobs"])


def _run_object_synthesis_job(
    *,
    run_id: str,
    osii_root: Path,
    file_id: str,
    synthesizer_name: str,
    expert_context: str | None,
    synthesizer_config: dict,
) -> None:
    try:
        run = get_run(run_id)
        if run is None:
            return

        run["status"] = "running"
        append_log(
            run_id, f"Starting synthesis for {file_id} using '{synthesizer_name}'"
        )

        synthesizer = get_synthesizer(synthesizer_name)
        result = synthesizer.synthesize(
            osii_store=osii_root,
            file_id=file_id,
            expert_context=expert_context,
            synthesizer_config=synthesizer_config,
        )

        run = get_run(run_id)
        if run is None:
            return

        run["status"] = "done"
        run["completed"] = 1
        run["items"][0]["status"] = "done"
        run["items"][0]["file_id"] = file_id
        run["items"][0]["synthesis"] = result.get("synthesis_rel") or result.get(
            "synth_rel"
        )
        append_log(run_id, "Synthesis complete.")

    except Exception as exc:
        run = get_run(run_id)
        if run is not None:
            run["status"] = "error"
            run["items"][0]["status"] = "error"
            run["items"][0]["error"] = str(exc)
        append_log(run_id, f"Synthesis failed: {exc}")


@router.post("/objects/{file_id}")
async def synthesize_object(request: Request, file_id: str, payload: dict):
    osii_root = request.app.state.osii_root.resolve()

    synthesizer_name = (payload.get("synthesizer_name") or "").strip()
    if not synthesizer_name:
        return {"error": "synthesizer_name is required"}

    expert_context = payload.get("expert_context")
    synthesizer_config = merged_processor_settings(
        osii_root,
        synthesizer_name,
        payload.get("synthesizer_config"),
    )

    run = create_run_record(
        [osii_root / "objects" / file_id], osii_root, osii_root, osii_root=osii_root
    )
    run["items"][0]["display"] = file_id

    thread = threading.Thread(
        target=_run_object_synthesis_job,
        kwargs={
            "run_id": run["id"],
            "osii_root": osii_root,
            "file_id": file_id,
            "synthesizer_name": synthesizer_name,
            "expert_context": expert_context,
            "synthesizer_config": synthesizer_config,
        },
        daemon=True,
    )
    thread.start()

    return {
        "run_id": run["id"],
        "status": run["status"],
        "file_id": file_id,
        "synthesizer_name": synthesizer_name,
    }
