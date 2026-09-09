from __future__ import annotations

from pathlib import Path
import tomllib

from osii.domain.read.catalog import load_files_catalog


def load_collection_definition(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(path.resolve())
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _file_id_by_source_relpath(osii_root: Path) -> dict[str, str]:
    out = {}
    for entry in load_files_catalog(osii_root):
        source_relpath = (entry.get("source_relpath") or "").strip().replace("\\", "/").strip("/")
        file_id = entry.get("file_id")
        if source_relpath and file_id:
            out[source_relpath] = file_id
    return out


def resolve_collection_members(osii_root: Path, payload: dict) -> list[str]:
    members = payload.get("members", [])
    if not isinstance(members, list):
        raise ValueError("'members' must be a list")

    relpath_map = _file_id_by_source_relpath(osii_root)

    file_ids: list[str] = []
    seen: set[str] = set()

    for item in members:
        if not isinstance(item, dict):
            raise ValueError("Each member entry must be an object")

        file_id = (item.get("file_id") or "").strip()
        source_relpath = (item.get("source_relpath") or "").strip().replace("\\", "/").strip("/")

        resolved_file_id = None

        if file_id:
            resolved_file_id = file_id
        elif source_relpath:
            resolved_file_id = relpath_map.get(source_relpath)
            if resolved_file_id is None:
                raise ValueError(f"Unknown source_relpath in collection file: {source_relpath}")
        else:
            raise ValueError("Each member must include either 'file_id' or 'source_relpath'")

        if resolved_file_id not in seen:
            seen.add(resolved_file_id)
            file_ids.append(resolved_file_id)

    return file_ids


def parse_collection_metadata(payload: dict) -> dict:
    collection = payload.get("collection", {})
    if not isinstance(collection, dict):
        raise ValueError("'collection' must be an object")

    name = (collection.get("name") or "").strip()
    if not name:
        raise ValueError("Collection name is required")

    description = collection.get("description")
    kind = (collection.get("kind") or "file-list").strip() or "file-list"
    color = collection.get("color")

    return {
        "name": name,
        "description": description,
        "kind": kind,
        "color": color,
    }