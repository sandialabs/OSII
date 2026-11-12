from fastapi import APIRouter, HTTPException, Request

from osii.indexing.common import embeddings_meta_path
from osii.indexing.chunking import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_CHUNKING_METHOD,
    validate_chunking_settings,
)

router = APIRouter(prefix="/api", tags=["embeddings"])


@router.post("/embeddings/build")
def build_embeddings(request: Request, payload: dict):
    from osii.domain.processing.standalone import submit_full_index

    try:
        batch_size = int(payload.get("batch_size", 64))
        chunking_method = str(payload.get("chunking_method") or DEFAULT_CHUNKING_METHOD)
        chunk_size = int(payload.get("chunk_size", DEFAULT_CHUNK_SIZE))
        chunk_overlap = int(payload.get("chunk_overlap", DEFAULT_CHUNK_OVERLAP))
        validate_chunking_settings(chunking_method, chunk_size, chunk_overlap)
        if not 1 <= batch_size <= 10000:
            raise ValueError("batch_size must be between 1 and 10,000")
        run = submit_full_index(
            request.app.state.osii_root.resolve(),
            batch_size=batch_size,
            chunking_method=chunking_method,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # Keep the old polling alias and in-progress status; run_id is immutable.
    return {
        "job_id": "segments",
        "status": "running",
        "run_id": run["id"],
        "queue_status": "queued",
    }


@router.get("/embeddings/build/{job_id}")
def get_embedding_build_status(request: Request, job_id: str):
    from osii.domain.processing.jobs import (
        configure_job_store,
        get_run,
        resolve_run_alias,
    )

    configure_job_store(request.app.state.osii_root.resolve())
    run_id = (
        resolve_run_alias("embeddings:segments") if job_id == "segments" else job_id
    )
    run = get_run(run_id) if run_id else None
    if run is None or run.get("tool_label") != "Full index rebuild":
        return {"error": f"Embedding job not found: {job_id}"}
    status = "running" if run["status"] in {"pending", "queued"} else run["status"]
    return {
        "status": status,
        "error": run.get("error"),
        "run_id": run["id"],
        "queue_status": run["status"],
        "progress": run.get("indexing_progress"),
    }


@router.get("/embeddings/meta")
async def embeddings_meta(request: Request):
    osii_root = request.app.state.osii_root.resolve()
    path = embeddings_meta_path(osii_root)
    if not path.exists():
        return {"error": "Embeddings metadata not found"}
    return {
        "index_path": str(path.parent / "segments.faiss"),
        "mapping_path": str(path.parent / "segments.mapping.jsonl"),
        "meta_path": str(path),
        "meta_text": path.read_text(encoding="utf-8"),
    }
