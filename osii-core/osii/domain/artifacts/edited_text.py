from __future__ import annotations

from pathlib import Path
import json

from osii.domain.read.manifest import list_text_records
from osii.domain.read.segments import get_segment_text
from osii.domain.storage.store import object_dir


def edited_text_path(osii_root: Path, file_id: str) -> Path:
    return object_dir(osii_root, file_id) / "edited_text.json"


def get_edited_text(osii_root: Path, file_id: str) -> dict | None:
    obj_dir = object_dir(osii_root, file_id)
    if not obj_dir.exists():
        return None

    path = edited_text_path(osii_root, file_id)
    if not path.exists():
        return {
            "file_id": file_id,
            "exists": False,
            "representation": "edited",
            "segments": [],
        }

    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "file_id": file_id,
        "exists": True,
        "representation": "edited",
        "segments": data.get("segments", []),
    }


def put_edited_text_segments(osii_root: Path, file_id: str, segments: list[dict]) -> dict | None:
    obj_dir = object_dir(osii_root, file_id)
    if not obj_dir.exists():
        return None

    valid_ids = {record.get("id") for record in list_text_records(osii_root, file_id)}

    normalized_segments = []
    for item in segments:
        if not isinstance(item, dict):
            raise ValueError("Each edited segment must be an object")

        seg_id = (item.get("id") or "").strip()
        text = item.get("text")

        if not seg_id:
            raise ValueError("Edited segment id is required")
        if seg_id not in valid_ids:
            raise ValueError(f"Unknown segment id: {seg_id}")
        if not isinstance(text, str):
            raise ValueError(f"Edited segment text must be a string for segment: {seg_id}")

        normalized_segments.append(
            {
                "id": seg_id,
                "text": text,
            }
        )

    path = edited_text_path(osii_root, file_id)
    path.write_text(
        json.dumps({"segments": normalized_segments}, indent=2),
        encoding="utf-8",
    )

    return {
        "file_id": file_id,
        "representation": "edited",
        "updated": True,
        "segments": normalized_segments,
    }


def delete_edited_text(osii_root: Path, file_id: str) -> dict | None:
    obj_dir = object_dir(osii_root, file_id)
    if not obj_dir.exists():
        return None

    path = edited_text_path(osii_root, file_id)
    removed = False
    if path.exists():
        path.unlink()
        removed = True

    return {
        "file_id": file_id,
        "representation": "edited",
        "removed": removed,
    }


def reconstruct_edited_full_text(osii_root: Path, file_id: str) -> str | None:
    edited = get_edited_text(osii_root, file_id)
    if edited is None or not edited.get("exists"):
        return None

    override_map = {
        item["id"]: item["text"]
        for item in edited.get("segments", [])
    }

    records = list_text_records(osii_root, file_id)
    parts = []

    for record in records:
        seg_id = record.get("id")
        if not seg_id:
            continue

        if seg_id in override_map:
            parts.append(override_map[seg_id])
            continue

        if seg_id.startswith("seg-"):
            try:
                seg_num = int(seg_id.removeprefix("seg-"))
            except Exception:
                continue
            text = get_segment_text(osii_root, file_id, seg_num)
            if text:
                parts.append(text)

    return "\n\n".join(parts).strip()