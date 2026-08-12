from io import BytesIO
from pathlib import Path
import zipfile

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from osii.domain.artifacts.collection_artifacts import get_collection_artifact_summary
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


def _write_directory_to_zip(archive: zipfile.ZipFile, directory: Path, prefix: str) -> None:
    if not directory.exists():
        return
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            archive.write(path, f"{prefix}/{path.relative_to(directory).as_posix()}")


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

    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        collection_dir = osii_root / "collections" / collection_id
        _write_directory_to_zip(archive, collection_dir, f"collections/{collection_id}")
        for file_id in list_collection_documents(osii_root, collection_id):
            _write_directory_to_zip(archive, osii_root / "objects" / file_id, f"objects/{file_id}")
    output.seek(0)
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
