import json
from pathlib import Path

from osii.domain.storage.store import manifest_jsonl_path, object_dir


def list_manifest_records(osii_store: Path, file_id: str) -> list[dict]:
    path = manifest_jsonl_path(osii_store, file_id)
    if not path.exists():
        return []

    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        items.append(json.loads(line))
    return items


def list_text_records(osii_store: Path, file_id: str) -> list[dict]:
    return [r for r in list_manifest_records(osii_store, file_id) if r.get("kind") == "text"]


def list_image_records(osii_store: Path, file_id: str) -> list[dict]:
    return [r for r in list_manifest_records(osii_store, file_id) if r.get("kind") == "image"]


def get_manifest_record_by_id(osii_store: Path, file_id: str, item_id: str) -> dict | None:
    for record in list_manifest_records(osii_store, file_id):
        if record.get("id") == item_id:
            return record
    return None


def get_record_path(osii_store: Path, file_id: str, record: dict) -> Path | None:
    rel_path = record.get("path")
    if not rel_path:
        return None

    path = object_dir(osii_store, file_id) / rel_path
    if not path.exists():
        return None

    return path