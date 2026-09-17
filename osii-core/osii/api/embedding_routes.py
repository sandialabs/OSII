import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from osii.indexing.common import embeddings_index_path, embeddings_mapping_path, embeddings_meta_path
from osii.build_vector_index import main as build_vector_index_main
from osii.indexing.chunking import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_CHUNKING_METHOD,
    validate_chunking_settings,
)

router = APIRouter(prefix="/api", tags=["embeddings"])

EMBEDDING_JOBS = {}


def _run_embedding_build(
    job_id: str,
    osii_root: Path,
    batch_size: int,
    chunking_method: str,
    chunk_size: int,
    chunk_overlap: int,
):
    try:
        import sys

        old_argv = sys.argv[:]
        sys.argv = [
            "build_vector_index",
            "--osii-root",
            str(osii_root),
            "--batch-size",
            str(batch_size),
            "--chunking-method",
            chunking_method,
            "--chunk-size",
            str(chunk_size),
            "--chunk-overlap",
            str(chunk_overlap),
        ]
        try:
            build_vector_index_main()
        finally:
            sys.argv = old_argv

        EMBEDDING_JOBS[job_id]["status"] = "done"
    except Exception as exc:
        EMBEDDING_JOBS[job_id]["status"] = "error"
        EMBEDDING_JOBS[job_id]["error"] = str(exc)


@router.post("/embeddings/build")
async def build_embeddings(request: Request, payload: dict):
    osii_root = request.app.state.osii_root.resolve()
    batch_size = int(payload.get("batch_size", 64))
    chunking_method = str(payload.get("chunking_method") or DEFAULT_CHUNKING_METHOD)
    chunk_size = int(payload.get("chunk_size", DEFAULT_CHUNK_SIZE))
    chunk_overlap = int(payload.get("chunk_overlap", DEFAULT_CHUNK_OVERLAP))
    try:
        validate_chunking_settings(chunking_method, chunk_size, chunk_overlap)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    job_id = "segments"

    EMBEDDING_JOBS[job_id] = {
        "status": "running",
        "error": None,
    }

    thread = threading.Thread(
        target=_run_embedding_build,
        kwargs={
            "job_id": job_id,
            "osii_root": osii_root,
            "batch_size": batch_size,
            "chunking_method": chunking_method,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        },
        daemon=True,
    )
    thread.start()

    return {
        "job_id": job_id,
        "status": "running",
    }


@router.get("/embeddings/build/{job_id}")
async def get_embedding_build_status(job_id: str):
    job = EMBEDDING_JOBS.get(job_id)
    if job is None:
        return {"error": f"Embedding job not found: {job_id}"}
    return job


@router.get("/embeddings/meta")
async def embeddings_meta(request: Request):
    osii_root = request.app.state.osii_root.resolve()
    path = embeddings_meta_path(osii_root)
    if not path.exists():
        return {"error": "Embeddings metadata not found"}
    return {
        "index_path": str(embeddings_index_path(osii_root)),
        "mapping_path": str(embeddings_mapping_path(osii_root)),
        "meta_path": str(path),
        "meta_text": path.read_text(encoding="utf-8"),
    }
