from __future__ import annotations

from pathlib import Path

from osii.domain.scopes.collections import list_collection_documents
from osii.domain.read.catalog import load_files_catalog, load_folders_catalog
from osii.domain.read.folders import get_folder_manifest
from osii.domain.scopes.scopes import (
    SCOPE_COLLECTION,
    SCOPE_FOLDER,
    SCOPE_OBJECT,
    SCOPE_ROOT,
    normalize_scope_type,
)


def _normalize_relpath(value: str | None) -> str:
    return (value or "").strip().replace("\\", "/").strip("/")


def _folder_scope_match(source_relpath: str, folder_relpath: str) -> bool:
    folder_relpath = _normalize_relpath(folder_relpath)
    source_relpath = _normalize_relpath(source_relpath)

    if folder_relpath == "":
        return True

    return source_relpath == folder_relpath or source_relpath.startswith(folder_relpath + "/")


def _resolve_folder_relpath(osii_root: Path, folder_id: str) -> str | None:
    for entry in load_folders_catalog(osii_root):
        if entry.get("folder_id") == folder_id:
            return _normalize_relpath(entry.get("path"))
    return None


def list_scope_file_ids(osii_root: Path, scope: dict) -> list[str]:
    scope_type = normalize_scope_type(scope.get("scope_type") or scope.get("type"))

    if scope_type == SCOPE_ROOT:
        return [
            entry["file_id"]
            for entry in load_files_catalog(osii_root)
            if entry.get("file_id")
        ]

    if scope_type == SCOPE_OBJECT:
        file_id = (scope.get("file_id") or "").strip()
        return [file_id] if file_id else []

    if scope_type == SCOPE_COLLECTION:
        collection_id = (scope.get("collection_id") or "").strip()
        if not collection_id:
            return []
        return list_collection_documents(osii_root, collection_id)

    if scope_type == SCOPE_FOLDER:
        folder_id = (scope.get("folder_id") or "").strip()
        if not folder_id:
            return []

        folder_relpath = _resolve_folder_relpath(osii_root, folder_id)
        if folder_relpath is None:
            return []

        results = []
        for entry in load_files_catalog(osii_root):
            file_id = entry.get("file_id")
            source_relpath = entry.get("source_relpath", "")
            if not file_id:
                continue
            if _folder_scope_match(source_relpath, folder_relpath):
                results.append(file_id)
        return results

    raise ValueError(f"Unsupported scope type: {scope_type}")