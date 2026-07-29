from __future__ import annotations

from pathlib import Path

from osii.domain.scopes.collections import get_collection
from osii.domain.read.catalog import load_folders_catalog
from osii.domain.scopes.scopes import (
    SCOPE_COLLECTION,
    SCOPE_FOLDER,
    SCOPE_OBJECT,
    SCOPE_ROOT,
    normalize_scope_type,
)


def describe_scope(osii_root: Path, scope: dict) -> dict:
    scope_type = normalize_scope_type(scope.get("scope_type") or scope.get("type"))

    if scope_type == SCOPE_ROOT:
        return {
            "scope_type": SCOPE_ROOT,
            "scope_id": "root",
            "label": "root",
        }

    if scope_type == SCOPE_OBJECT:
        file_id = (scope.get("file_id") or "").strip()
        return {
            "scope_type": SCOPE_OBJECT,
            "scope_id": file_id,
            "file_id": file_id,
            "label": file_id,
        }

    if scope_type == SCOPE_FOLDER:
        folder_id = (scope.get("folder_id") or "").strip()
        for entry in load_folders_catalog(osii_root):
            if entry.get("folder_id") == folder_id:
                relpath = entry.get("path") or ""
                label = relpath if relpath else "root-folder"
                return {
                    "scope_type": SCOPE_FOLDER,
                    "scope_id": folder_id,
                    "folder_id": folder_id,
                    "path": relpath,
                    "label": label,
                }
        return {
            "scope_type": SCOPE_FOLDER,
            "scope_id": folder_id,
            "folder_id": folder_id,
            "label": folder_id,
        }

    if scope_type == SCOPE_COLLECTION:
        collection_id = (scope.get("collection_id") or "").strip()
        collection = get_collection(osii_root, collection_id)
        return {
            "scope_type": SCOPE_COLLECTION,
            "scope_id": collection_id,
            "collection_id": collection_id,
            "label": collection["name"] if collection else collection_id,
        }

    raise ValueError(f"Unsupported scope type: {scope_type}")