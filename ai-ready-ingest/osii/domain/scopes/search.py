from __future__ import annotations

from pathlib import Path

from osii.domain.scopes.collections import list_collection_documents
from osii.domain.read.catalog import load_folders_catalog
from osii.domain.scopes.scopes import (
    SCOPE_COLLECTION,
    SCOPE_FOLDER,
    SCOPE_OBJECT,
    SCOPE_ROOT,
    normalize_scope_type,
)


def _normalize_relpath(value: str | None) -> str:
    return (value or "").strip().replace("\\", "/").strip("/")


def folder_scope_match(source_relpath: str, folder_relpath: str) -> bool:
    folder_relpath = _normalize_relpath(folder_relpath)
    source_relpath = _normalize_relpath(source_relpath)

    if folder_relpath == "":
        return True

    return source_relpath == folder_relpath or source_relpath.startswith(folder_relpath + "/")


def resolve_folder_relpath(osii_root: Path, folder_id: str | None) -> str | None:
    if not folder_id:
        return None

    for entry in load_folders_catalog(osii_root):
        if entry.get("folder_id") == folder_id:
            return _normalize_relpath(entry.get("path"))
    return None


def build_scope_filters(osii_root: Path, scope: dict | None) -> dict:
    scope = scope or {}
    scope_type = normalize_scope_type(scope.get("scope_type") or scope.get("type") or SCOPE_ROOT)

    if scope_type == SCOPE_ROOT:
        return {
            "scope_type": SCOPE_ROOT,
            "folder_relpath": None,
            "collection_members": None,
            "object_file_id": None,
        }

    if scope_type == SCOPE_OBJECT:
        file_id = (scope.get("file_id") or "").strip()
        return {
            "scope_type": SCOPE_OBJECT,
            "folder_relpath": None,
            "collection_members": None,
            "object_file_id": file_id or None,
        }

    if scope_type == SCOPE_FOLDER:
        folder_id = (scope.get("folder_id") or "").strip()
        return {
            "scope_type": SCOPE_FOLDER,
            "folder_relpath": resolve_folder_relpath(osii_root, folder_id),
            "collection_members": None,
            "object_file_id": None,
        }

    if scope_type == SCOPE_COLLECTION:
        collection_id = (scope.get("collection_id") or "").strip()
        members = set(list_collection_documents(osii_root, collection_id)) if collection_id else set()
        return {
            "scope_type": SCOPE_COLLECTION,
            "folder_relpath": None,
            "collection_members": members,
            "object_file_id": None,
        }

    raise ValueError(f"Unsupported scope type: {scope_type}")


def file_matches_scope(
    *,
    file_id: str,
    source_relpath: str,
    scope_filters: dict,
) -> bool:
    object_file_id = scope_filters.get("object_file_id")
    folder_relpath = scope_filters.get("folder_relpath")
    collection_members = scope_filters.get("collection_members")

    if object_file_id is not None and file_id != object_file_id:
        return False

    if folder_relpath is not None and not folder_scope_match(source_relpath, folder_relpath):
        return False

    if collection_members is not None and file_id not in collection_members:
        return False

    return True