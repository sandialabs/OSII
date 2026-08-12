from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import uuid

import tomli_w
import tomllib

from osii.domain.artifacts.enrichment_artifacts import write_object_enrichment_variant
from osii.domain.storage.store import object_dir


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _sets_path(osii_root: Path) -> Path:
    return osii_root / "keyword_sets.toml"


def _clean_keywords(values: object) -> list[str]:
    if not isinstance(values, list):
        raise ValueError("keywords must be a list")
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        keyword = str(value).strip()
        if not keyword or len(keyword) > 120:
            raise ValueError("Each keyword must be between 1 and 120 characters.")
        key = keyword.casefold()
        if key not in seen:
            seen.add(key)
            result.append(keyword)
    return result


def list_keyword_sets(osii_root: Path) -> list[dict]:
    path = _sets_path(osii_root)
    if not path.exists():
        return []
    try:
        values = tomllib.loads(path.read_text(encoding="utf-8")).get("keyword_sets", {}).get("sets", [])
    except (OSError, tomllib.TOMLDecodeError):
        return []
    return [item for item in values if isinstance(item, dict) and item.get("id") and item.get("name")]


def _write_sets(osii_root: Path, sets: list[dict]) -> None:
    _atomic_write(_sets_path(osii_root), tomli_w.dumps({"keyword_sets": {"sets": sets}}))


def create_keyword_set(osii_root: Path, *, name: str, keywords: object) -> dict:
    name = str(name or "").strip()
    if not name or len(name) > 120:
        raise ValueError("Keyword set name must be between 1 and 120 characters.")
    cleaned = _clean_keywords(keywords)
    if not cleaned:
        raise ValueError("A keyword set needs at least one keyword.")
    sets = list_keyword_sets(osii_root)
    if any(item["name"].casefold() == name.casefold() for item in sets):
        raise ValueError("A keyword set with that name already exists.")
    record = {"id": f"keywords-{uuid.uuid4().hex[:12]}", "name": name, "keywords": cleaned}
    sets.append(record)
    _write_sets(osii_root, sets)
    return record


def delete_keyword_set(osii_root: Path, set_id: str) -> bool:
    sets = list_keyword_sets(osii_root)
    retained = [item for item in sets if item["id"] != set_id]
    if len(sets) == len(retained):
        return False
    _write_sets(osii_root, retained)
    return True


def get_manual_keywords(osii_root: Path, file_id: str) -> list[str] | None:
    if not object_dir(osii_root, file_id).exists():
        return None
    path = object_dir(osii_root, file_id) / "enrichments" / "keywords--manual.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return _clean_keywords(data.get("keywords", []))
    except (OSError, json.JSONDecodeError, ValueError):
        return []


def write_manual_keywords(osii_root: Path, file_id: str, keywords: object) -> list[str] | None:
    if not object_dir(osii_root, file_id).exists():
        return None
    cleaned = _clean_keywords(keywords)
    write_object_enrichment_variant(
        osii_root,
        file_id,
        kind="keywords",
        method="manual",
        payload={"kind": "keywords", "method": "manual", "keywords": cleaned},
        metadata={"managed_by": "user"},
    )
    return cleaned
