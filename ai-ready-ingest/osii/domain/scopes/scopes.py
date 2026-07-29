from __future__ import annotations

from typing import Final


SCOPE_ROOT: Final[str] = "root"
SCOPE_FOLDER: Final[str] = "folder"
SCOPE_COLLECTION: Final[str] = "collection"
SCOPE_OBJECT: Final[str] = "object"
SCOPE_DOCUMENT: Final[str] = "document"

VALID_SCOPE_TYPES: Final[set[str]] = {
    SCOPE_ROOT,
    SCOPE_FOLDER,
    SCOPE_COLLECTION,
    SCOPE_OBJECT,
    SCOPE_DOCUMENT,
}


def is_valid_scope_type(value: str | None) -> bool:
    return (value or "").strip().lower() in VALID_SCOPE_TYPES


def normalize_scope_type(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized == SCOPE_DOCUMENT:
        return SCOPE_OBJECT
    if normalized not in VALID_SCOPE_TYPES:
        raise ValueError(f"Unsupported scope type: {value}")
    return normalized


def make_root_scope() -> dict:
    return {
        "scope_type": SCOPE_ROOT,
        "scope_id": "root",
    }


def make_folder_scope(folder_id: str) -> dict:
    folder_id = (folder_id or "").strip()
    if not folder_id:
        raise ValueError("folder_id is required")
    return {
        "scope_type": SCOPE_FOLDER,
        "scope_id": folder_id,
        "folder_id": folder_id,
    }


def make_collection_scope(collection_id: str) -> dict:
    collection_id = (collection_id or "").strip()
    if not collection_id:
        raise ValueError("collection_id is required")
    return {
        "scope_type": SCOPE_COLLECTION,
        "scope_id": collection_id,
        "collection_id": collection_id,
    }


def make_object_scope(file_id: str) -> dict:
    file_id = (file_id or "").strip()
    if not file_id:
        raise ValueError("file_id is required")
    return {
        "scope_type": SCOPE_OBJECT,
        "scope_id": file_id,
        "file_id": file_id,
    }