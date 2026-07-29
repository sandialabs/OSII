from __future__ import annotations

from pathlib import Path
import json

from osii.domain.storage.store import (
    collection_enrichments_dir,
    folder_enrichments_dir,
    object_enrichments_dir,
    root_enrichments_dir,
)
from osii.domain.scopes.scopes import normalize_scope_type


def _list_enrichment_dir(path: Path, rel_prefix: str) -> list[dict]:
    if not path.exists():
        return []

    items = []

    for child in sorted(path.iterdir(), key=lambda p: p.name.lower()):
        if child.is_dir():
            files = []
            for sub in sorted(child.iterdir(), key=lambda p: p.name.lower()):
                files.append(
                    {
                        "name": sub.name,
                        "relpath": f"{rel_prefix}/{child.name}/{sub.name}",
                        "is_dir": sub.is_dir(),
                    }
                )
            items.append(
                {
                    "name": child.name,
                    "kind": "bundle",
                    "relpath": f"{rel_prefix}/{child.name}",
                    "files": files,
                }
            )
        else:
            items.append(
                {
                    "name": child.name,
                    "kind": "file",
                    "relpath": f"{rel_prefix}/{child.name}",
                }
            )

    return items


def list_scope_enrichments(osii_root: Path, scope: dict) -> list[dict]:
    scope_type = normalize_scope_type(scope.get("scope_type") or scope.get("type"))

    if scope_type == "object":
        file_id = scope["file_id"]
        return _list_enrichment_dir(
            object_enrichments_dir(osii_root, file_id),
            f"objects/{file_id}/enrichments",
        )

    if scope_type == "folder":
        folder_id = scope["folder_id"]
        return _list_enrichment_dir(
            folder_enrichments_dir(osii_root, folder_id),
            f"folders/folder-{folder_id}.enrichments",
        )

    if scope_type == "collection":
        collection_id = scope["collection_id"]
        return _list_enrichment_dir(
            collection_enrichments_dir(osii_root, collection_id),
            f"collections/{collection_id}/enrichments",
        )

    if scope_type == "root":
        return _list_enrichment_dir(
            root_enrichments_dir(osii_root),
            "enrichments",
        )

    raise ValueError(f"Unsupported scope type: {scope_type}")


def _read_json_if_exists(path: Path):
    if not path.exists() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_object_enrichment_payload(osii_root: Path, file_id: str, filename: str) -> dict | None:
    path = object_enrichments_dir(osii_root, file_id) / filename
    data = _read_json_if_exists(path)
    if data is None:
        return None

    return {
        "file_id": file_id,
        "filename": filename,
        "relpath": f"objects/{file_id}/enrichments/{filename}",
        "data": data,
    }


def get_scope_enrichment_payload(osii_root: Path, scope: dict, filename: str) -> dict | None:
    scope_type = normalize_scope_type(scope.get("scope_type") or scope.get("type"))
    if Path(filename).name != filename:
        raise ValueError("filename must not contain a path")

    if scope_type == "object":
        base_dir = object_enrichments_dir(osii_root, scope["file_id"])
        scope_id = scope["file_id"]
        rel_prefix = f"objects/{scope_id}/enrichments"
    elif scope_type == "folder":
        base_dir = folder_enrichments_dir(osii_root, scope["folder_id"])
        scope_id = scope["folder_id"]
        rel_prefix = f"folders/folder-{scope_id}.enrichments"
    elif scope_type == "collection":
        base_dir = collection_enrichments_dir(osii_root, scope["collection_id"])
        scope_id = scope["collection_id"]
        rel_prefix = f"collections/{scope_id}/enrichments"
    elif scope_type == "root":
        base_dir = root_enrichments_dir(osii_root)
        scope_id = "root"
        rel_prefix = "enrichments"
    else:
        raise ValueError(f"Unsupported scope type: {scope_type}")

    data = _read_json_if_exists(base_dir / filename)
    if data is None:
        return None
    return {
        "scope_type": scope_type,
        "scope_id": scope_id,
        "filename": filename,
        "relpath": f"{rel_prefix}/{filename}",
        "data": data,
    }
