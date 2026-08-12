from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import tomllib

import tomli_w

from osii.domain.storage.atomic import atomic_write_text


def _governance_path(osii_root: Path, file_id: str) -> Path:
    return osii_root.resolve() / "objects" / file_id / "governance.toml"


def _clean_values(values: object) -> list[str]:
    if not isinstance(values, list):
        raise ValueError("labels and tags must be lists")
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value).strip()
        key = clean.casefold()
        if clean and key not in seen:
            result.append(clean)
            seen.add(key)
    return result


def get_governance(osii_root: Path, file_id: str) -> dict | None:
    object_dir = osii_root.resolve() / "objects" / file_id
    if not object_dir.is_dir():
        return None
    path = _governance_path(osii_root, file_id)
    if not path.exists():
        return {
            "sensitivity_labels": [],
            "tags": [],
            "handling_notes": "",
            "updated_utc": None,
        }
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8")).get("governance", {})
    except (OSError, tomllib.TOMLDecodeError):
        payload = {}
    return {
        "sensitivity_labels": _clean_values(payload.get("sensitivity_labels", [])),
        "tags": _clean_values(payload.get("tags", [])),
        "handling_notes": str(payload.get("handling_notes") or "").strip(),
        "updated_utc": payload.get("updated_utc"),
    }


def write_governance(
    osii_root: Path,
    file_id: str,
    *,
    sensitivity_labels: object,
    tags: object,
    handling_notes: object = "",
) -> dict | None:
    current = get_governance(osii_root, file_id)
    if current is None:
        return None
    record = {
        "sensitivity_labels": _clean_values(sensitivity_labels),
        "tags": _clean_values(tags),
        "handling_notes": str(handling_notes or "").strip(),
        "updated_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    atomic_write_text(
        _governance_path(osii_root, file_id),
        tomli_w.dumps({"governance": record}),
    )
    return record


def merge_governance(osii_root: Path, file_id: str, incoming: dict) -> dict | None:
    current = get_governance(osii_root, file_id)
    if current is None:
        return None

    def union(first: list[str], second: object) -> list[str]:
        return _clean_values([*first, *_clean_values(second if isinstance(second, list) else [])])

    incoming_notes = str(incoming.get("handling_notes") or "").strip()
    notes = current["handling_notes"]
    if incoming_notes and incoming_notes.casefold() not in notes.casefold():
        notes = f"{notes}\n\nImported note: {incoming_notes}".strip()
    return write_governance(
        osii_root,
        file_id,
        sensitivity_labels=union(current["sensitivity_labels"], incoming.get("sensitivity_labels", [])),
        tags=union(current["tags"], incoming.get("tags", [])),
        handling_notes=notes,
    )
