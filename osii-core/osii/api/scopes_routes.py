from fastapi import APIRouter, Request

from osii.domain.artifacts.scope_artifacts import get_scope_artifact_summary
from osii.domain.read.catalog import load_folders_catalog
from osii.domain.scopes.collections import list_collections
from osii.domain.scopes.descriptors import describe_scope
from osii.domain.scopes.membership import list_scope_file_ids
from osii.domain.scopes.summaries import get_scope_object_summaries

router = APIRouter(prefix="/api/scopes", tags=["scopes"])


@router.get("/root")
async def get_root_scope(request: Request):
    osii_root = request.app.state.osii_root.resolve()
    scope = {"scope_type": "root"}
    return {
        "scope": describe_scope(osii_root, scope),
        "member_file_ids": list_scope_file_ids(osii_root, scope),
    }


@router.get("/folders")
async def get_folder_scopes(request: Request):
    osii_root = request.app.state.osii_root.resolve()
    folders = load_folders_catalog(osii_root)

    return {
        "scopes": [
            {
                "scope_type": "folder",
                "scope_id": entry.get("folder_id"),
                "folder_id": entry.get("folder_id"),
                "path": entry.get("path") or "",
                "label": (entry.get("path") or "").strip("/") or "root-folder",
            }
            for entry in folders
            if entry.get("folder_id")
        ]
    }


@router.get("/collections")
async def get_collection_scopes(request: Request):
    osii_root = request.app.state.osii_root.resolve()
    collections = list_collections(osii_root)

    return {
        "scopes": [
            {
                "scope_type": "collection",
                "scope_id": item["id"],
                "collection_id": item["id"],
                "label": item["name"],
                "kind": item.get("kind", "manual"),
                "description": item.get("description"),
                "document_count": item.get("document_count", 0),
            }
            for item in collections
        ]
    }


@router.post("/describe")
async def describe_scope_route(request: Request, payload: dict):
    osii_root = request.app.state.osii_root.resolve()
    return {
        "scope": describe_scope(osii_root, payload),
        "member_file_ids": list_scope_file_ids(osii_root, payload),
    }


@router.post("/summaries")
async def scope_summaries_route(request: Request, payload: dict):
    osii_root = request.app.state.osii_root.resolve()
    try:
        return get_scope_object_summaries(osii_root, payload.get("scope") or payload)
    except ValueError as exc:
        return {"error": str(exc)}


@router.post("/artifacts")
async def scope_artifacts_route(request: Request, payload: dict):
    osii_root = request.app.state.osii_root.resolve()
    try:
        return get_scope_artifact_summary(osii_root, payload.get("scope") or payload)
    except ValueError as exc:
        return {"error": str(exc)}