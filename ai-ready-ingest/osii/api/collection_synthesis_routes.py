import threading
from pathlib import Path

from fastapi import APIRouter, Request

from osii.domain.artifacts.collection_artifacts import get_collection_artifact_summary, list_collection_syntheses
from osii.domain.processing.jobs import append_log, create_run_record, get_run
from osii.domain.scopes.collections import get_collection
from osii.synthesis.collection.firstn import CollectionFirstNSynthesizer

router = APIRouter(prefix="/api/collections", tags=["collection-synthesis"])


def _run_collection_synthesis_job(
    *,
    run_id: str,
    osii_root: Path,
    collection_id: str,
    synthesizer_name: str,
    expert_context: str | None,
    synthesizer_config: dict,
) -> None:
    try:
        run = get_run(run_id)
        if run is None:
            return

        run["status"] = "running"
        append_log(run_id, f"Starting collection synthesis for {collection_id} using '{synthesizer_name}'")

        if synthesizer_name == "collection_firstn":
            synthesizer = CollectionFirstNSynthesizer()
            result = synthesizer.synthesize_collection(
                osii_store=osii_root,
                collection_id=collection_id,
                expert_context=expert_context,
                synthesizer_config=synthesizer_config,
            )
        else:
            raise RuntimeError(f"Unsupported collection synthesizer: {synthesizer_name}")

        run = get_run(run_id)
        if run is None:
            return

        run["status"] = "done"
        run["completed"] = 1
        run["items"][0]["status"] = "done"
        run["items"][0]["synthesis"] = result
        append_log(run_id, "Collection synthesis complete.")

    except Exception as exc:
        run = get_run(run_id)
        if run is not None:
            run["status"] = "error"
            run["items"][0]["status"] = "error"
            run["items"][0]["error"] = str(exc)
        append_log(run_id, f"Collection synthesis failed: {exc}")


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
async def run_collection_synthesis_route(request: Request, collection_id: str, payload: dict):
    osii_root = request.app.state.osii_root.resolve()

    collection = get_collection(osii_root, collection_id)
    if collection is None:
        return {"error": "unknown collection_id"}

    synthesizer_name = (payload.get("synthesizer_name") or "collection_firstn").strip()
    expert_context = payload.get("expert_context")
    synthesizer_config = payload.get("synthesizer_config") or {}

    run = create_run_record([osii_root], osii_root, osii_root, osii_root=osii_root)
    run["items"][0]["display"] = f"collection:{collection_id}"

    thread = threading.Thread(
        target=_run_collection_synthesis_job,
        kwargs={
            "run_id": run["id"],
            "osii_root": osii_root,
            "collection_id": collection_id,
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
        "collection_id": collection_id,
        "synthesizer_name": synthesizer_name,
    }
