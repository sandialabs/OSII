from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sqlite3
import shutil
import tempfile
import tomllib
import uuid

import tomli_w

from osii.domain.catalog_db import (
    get_collection_member_ids,
    get_collection_record,
    get_file_collection_records,
    list_collection_records,
    rebuild_catalog,
)


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_collections_dir(osii_root: Path) -> Path:
    path = (osii_root / "collections").resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_collections_db_path(osii_root: Path) -> Path:
    """Return the retired legacy path so migration and diagnostics can find it."""
    return (osii_root / ".collections" / "collections.sqlite").resolve()


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _collection_dir(osii_root: Path, collection_id: str) -> Path:
    return get_collections_dir(osii_root) / collection_id


def _collection_path(osii_root: Path, collection_id: str) -> Path:
    return _collection_dir(osii_root, collection_id) / "collection.toml"


def _members_path(osii_root: Path, collection_id: str) -> Path:
    return _collection_dir(osii_root, collection_id) / "members.jsonl"


def _write_collection(osii_root: Path, record: dict) -> None:
    serializable = {key: value for key, value in record.items() if value is not None and key != "document_count"}
    _atomic_write(_collection_path(osii_root, record["id"]), tomli_w.dumps({"collection": serializable}))


def _read_collection(path: Path) -> dict | None:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    record = dict(data.get("collection", data))
    if not record.get("id"):
        record["id"] = path.parent.name
    return record


def _read_members(osii_root: Path, collection_id: str) -> list[dict]:
    path = _members_path(osii_root, collection_id)
    if not path.exists():
        return []
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("file_id"):
            records.append(item)
    return records


def _write_members(osii_root: Path, collection_id: str, records: list[dict]) -> None:
    content = "".join(json.dumps(record, sort_keys=True) + "\n" for record in records)
    _atomic_write(_members_path(osii_root, collection_id), content)


def _migrate_legacy_database(osii_root: Path) -> int:
    legacy = get_collections_db_path(osii_root)
    marker = get_collections_dir(osii_root) / ".legacy-migrated"
    if not legacy.exists() or marker.exists():
        return 0
    migrated = 0
    try:
        conn = sqlite3.connect(legacy)
        conn.row_factory = sqlite3.Row
        columns = {row[1] for row in conn.execute("PRAGMA table_info(collections)")}
        for row in conn.execute("SELECT * FROM collections"):
            record = {
                "id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "kind": row["kind"] if "kind" in columns else "manual",
                "color": row["color"],
                "created_utc": row["created_utc"],
                "updated_utc": row["updated_utc"],
            }
            if not _collection_path(osii_root, row["id"]).exists():
                _write_collection(osii_root, record)
                members = [dict(member) for member in conn.execute("SELECT file_id, created_utc FROM collection_documents WHERE collection_id = ? ORDER BY created_utc, file_id", (row["id"],))]
                _write_members(osii_root, row["id"], members)
                migrated += 1
        conn.close()
    except sqlite3.DatabaseError:
        return 0
    _atomic_write(marker, f"migrated_utc={utc_now_iso()}\ncollections={migrated}\n")
    return migrated


def init_collections_db(osii_root: Path) -> Path:
    """Compatibility entry point: migrate legacy SQLite into canonical files."""
    directory = get_collections_dir(osii_root)
    if _migrate_legacy_database(osii_root):
        rebuild_catalog(osii_root)
    return directory


def list_collections(osii_root: Path) -> list[dict]:
    init_collections_db(osii_root)
    return list_collection_records(osii_root)


def create_collection(osii_root: Path, *, name: str, description: str | None = None, kind: str = "manual", color: str | None = None) -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("Collection name is required.")
    if any(item["name"].lower() == name.lower() for item in list_collections(osii_root)):
        raise sqlite3.IntegrityError("Collection name already exists.")
    now = utc_now_iso()
    record = {"id": f"col-{uuid.uuid4().hex[:12]}", "name": name, "description": description, "kind": (kind or "manual").strip() or "manual", "color": color, "created_utc": now, "updated_utc": now}
    _write_collection(osii_root, record)
    _write_members(osii_root, record["id"], [])
    rebuild_catalog(osii_root)
    return {**record, "document_count": 0}


def get_collection(osii_root: Path, collection_id: str) -> dict | None:
    init_collections_db(osii_root)
    return get_collection_record(osii_root, collection_id)


def update_collection(osii_root: Path, collection_id: str, *, name: str | None = None, description: str | None = None, kind: str | None = None, color: str | None = None) -> dict | None:
    record = get_collection(osii_root, collection_id)
    if not record:
        return None
    if name is not None:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Collection name may not be empty.")
        if any(item["id"] != collection_id and item["name"].lower() == clean_name.lower() for item in list_collections(osii_root)):
            raise sqlite3.IntegrityError("Collection name already exists.")
        record["name"] = clean_name
    if description is not None:
        record["description"] = description
    if kind is not None:
        record["kind"] = kind.strip() or "manual"
    if color is not None:
        record["color"] = color
    record["updated_utc"] = utc_now_iso()
    _write_collection(osii_root, record)
    rebuild_catalog(osii_root)
    return get_collection(osii_root, collection_id)


def delete_collection(osii_root: Path, collection_id: str) -> bool:
    directory = _collection_dir(osii_root, collection_id)
    if not directory.exists():
        return False
    shutil.rmtree(directory)
    rebuild_catalog(osii_root)
    return True


def list_collection_documents(osii_root: Path, collection_id: str) -> list[str]:
    init_collections_db(osii_root)
    return get_collection_member_ids(osii_root, collection_id)


def add_documents_to_collection(osii_root: Path, collection_id: str, file_ids: list[str]) -> dict:
    if get_collection(osii_root, collection_id) is None:
        raise ValueError(f"Collection not found: {collection_id}")
    records = _read_members(osii_root, collection_id)
    existing = {str(item["file_id"]) for item in records}
    added: list[str] = []
    already_present: list[str] = []
    for file_id in file_ids:
        if file_id in existing:
            already_present.append(file_id)
        else:
            records.append({"file_id": file_id, "created_utc": utc_now_iso()})
            existing.add(file_id)
            added.append(file_id)
    _write_members(osii_root, collection_id, records)
    rebuild_catalog(osii_root)
    return {"collection_id": collection_id, "added": added, "already_present": already_present}


def remove_document_from_collection(osii_root: Path, collection_id: str, file_id: str) -> dict:
    records = _read_members(osii_root, collection_id)
    retained = [item for item in records if str(item["file_id"]) != file_id]
    removed = len(retained) != len(records)
    if removed:
        _write_members(osii_root, collection_id, retained)
        rebuild_catalog(osii_root)
    return {"collection_id": collection_id, "file_id": file_id, "removed": removed}


def list_collections_for_file(osii_root: Path, file_id: str) -> list[dict]:
    init_collections_db(osii_root)
    return get_file_collection_records(osii_root, file_id)
