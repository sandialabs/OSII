from io import BytesIO

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from osii.domain.artifacts.collection_artifacts import get_collection_artifact_summary
from osii.domain.osii_packages import create_collection_package
from osii.domain.scopes.collections import (
    add_documents_to_collection,
    create_collection,
    delete_collection,
    get_collection,
    list_collection_documents,
    list_collections,
    remove_document_from_collection,
    update_collection,
)

router = APIRouter(prefix="/api/collections", tags=["collections"])


def _safe_export_name(value: str) -> str:
    return "".join(char if (char.isascii() and char.isalnum()) or char in "-_" else "-" for char in value).strip("-") or "collection"


@router.get("")
async def get_collections(request: Request):
    osii_root = request.app.state.osii_root.resolve()
    return {"collections": list_collections(osii_root)}


@router.post("")
async def post_collection(request: Request, payload: dict):
    osii_root = request.app.state.osii_root.resolve()

    try:
        collection = create_collection(
            osii_root,
            name=payload.get("name", ""),
            description=payload.get("description"),
            kind=payload.get("kind", "manual"),
            color=payload.get("color"),
        )
    except ValueError as exc:
        return {"error": str(exc)}

    return {"collection": collection}


@router.get("/{collection_id}")
async def get_collection_route(request: Request, collection_id: str):
    osii_root = request.app.state.osii_root.resolve()
    collection = get_collection(osii_root, collection_id)
    if collection is None:
        return {"error": "unknown collection_id"}

    artifact_summary = get_collection_artifact_summary(osii_root, collection_id)

    return {
        "collection": collection,
        "artifact_summary": artifact_summary,
    }


@router.get("/{collection_id}/export")
async def export_collection_sidecar(request: Request, collection_id: str):
    """Export only the selected collection's OSII sidecar; source files stay out of the archive."""
    osii_root = request.app.state.osii_root.resolve()
    collection = get_collection(osii_root, collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail="unknown collection_id")

    output = BytesIO(create_collection_package(osii_root, collection_id))
    filename = f"{_safe_export_name(collection['name'])}-osii-sidecar.zip"
    return StreamingResponse(
        output,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.patch("/{collection_id}")
async def patch_collection(request: Request, collection_id: str, payload: dict):
    osii_root = request.app.state.osii_root.resolve()

    try:
        collection = update_collection(
            osii_root,
            collection_id,
            name=payload.get("name"),
            description=payload.get("description"),
            kind=payload.get("kind"),
            color=payload.get("color"),
        )
    except ValueError as exc:
        return {"error": str(exc)}

    if collection is None:
        return {"error": "unknown collection_id"}

    return {"collection": collection}


@router.delete("/{collection_id}")
async def delete_collection_route(request: Request, collection_id: str):
    osii_root = request.app.state.osii_root.resolve()
    ok = delete_collection(osii_root, collection_id)
    if not ok:
        return {"error": "unknown collection_id"}
    return {"ok": True}


@router.get("/{collection_id}/members")
async def get_collection_members(request: Request, collection_id: str):
    osii_root = request.app.state.osii_root.resolve()
    collection = get_collection(osii_root, collection_id)
    if collection is None:
        return {"error": "unknown collection_id"}

    return {
        "collection": collection,
        "file_ids": list_collection_documents(osii_root, collection_id),
    }


@router.post("/{collection_id}/members")
async def post_collection_members(request: Request, collection_id: str, payload: dict):
    osii_root = request.app.state.osii_root.resolve()
    collection = get_collection(osii_root, collection_id)
    if collection is None:
        return {"error": "unknown collection_id"}

    file_ids = payload.get("file_ids", [])
    if not isinstance(file_ids, list):
        return {"error": "file_ids must be a list"}

    return add_documents_to_collection(osii_root, collection_id, file_ids)


@router.delete("/{collection_id}/members/{file_id}")
async def delete_collection_member(request: Request, collection_id: str, file_id: str):
    osii_root = request.app.state.osii_root.resolve()
    collection = get_collection(osii_root, collection_id)
    if collection is None:
        return {"error": "unknown collection_id"}

    return remove_document_from_collection(osii_root, collection_id, file_id)


@router.post("/{collection_id}/process")
async def process_collection(request: Request, collection_id: str, payload: dict):
    """Explicit reprocessing belongs to collection status, never simple Intake."""
    from starlette.concurrency import run_in_threadpool
    from osii.api.runs_routes import _start_run
    from osii.domain.artifacts.source_files import get_source_file_path
    def prepare():
        root = request.app.state.osii_root.resolve()
        if get_collection(root, collection_id) is None:
            raise HTTPException(404, "Collection not found")
        members = list_collection_documents(root, collection_id)
        if not members or len(members) > 10000:
            raise HTTPException(422, "Choose a collection with 1 to 10,000 documents")
        paths, missing = [], []
        for file_id in members:
            path = get_source_file_path(root, request.app.state.shared_volume_root, request.app.state.upload_originals_root, file_id)
            if path is None:
                missing.append(file_id)
            else:
                paths.append(str(path))
        if missing:
            raise HTTPException(409, {"message": "Original files unavailable. Existing collection results are unchanged.", "file_ids": missing})
        mode = payload.get("mode", "missing")
        if mode not in {"missing", "reprocess"}:
            raise HTTPException(422, "Choose missing or reprocess")
        return _start_run(request, {"workflow": "library", "queue_paths": paths, "include_subfolders": False,
            "processing_flow_id": payload.get("processing_flow_id", "bundled"), "extract_mode": mode,
            "extraction_policy": "auto", "target_collection_id": collection_id})
    return await run_in_threadpool(prepare)
