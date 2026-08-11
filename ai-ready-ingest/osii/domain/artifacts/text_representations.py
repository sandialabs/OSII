from __future__ import annotations

from pathlib import Path

from osii.domain.artifacts.edited_text import edited_text_path, reconstruct_edited_full_text
from osii.domain.artifacts.extraction_variants import list_extraction_variants, primary_extraction_dir
from osii.domain.storage.store import object_dir, object_text_path


def canonical_text_record(osii_root: Path, file_id: str) -> dict:
    path = object_text_path(osii_root, file_id)
    return {
        "name": "canonical",
        "kind": "canonical_extracted_text",
        "path": f"objects/{file_id}/text.txt",
        "exists": path.exists(),
        "preferred": not edited_text_path(osii_root, file_id).exists(),
    }


def edited_text_record(osii_root: Path, file_id: str) -> dict:
    path = edited_text_path(osii_root, file_id)
    return {
        "name": "edited",
        "kind": "edited_text",
        "path": f"objects/{file_id}/edited_text.json",
        "exists": path.exists(),
        "preferred": path.exists(),
    }


def list_text_representations(osii_root: Path, file_id: str) -> list[dict] | None:
    obj_dir = object_dir(osii_root, file_id)
    if not obj_dir.exists():
        return None

    return [canonical_text_record(osii_root, file_id), edited_text_record(osii_root, file_id)]


def get_preferred_text_representation(osii_root: Path, file_id: str) -> dict | None:
    obj_dir = object_dir(osii_root, file_id)
    if not obj_dir.exists():
        return None

    edited_path = edited_text_path(osii_root, file_id)
    if edited_path.exists():
        edited_text = reconstruct_edited_full_text(osii_root, file_id)
        return {
            "name": "edited",
            "kind": "edited_text",
            "path": f"objects/{file_id}/edited_text.json",
            "text": edited_text or "",
        }

    primary = primary_extraction_dir(osii_root, file_id)
    canonical = (primary / "text.txt") if primary else object_text_path(osii_root, file_id)
    if canonical.exists():
        return {
            "name": "canonical",
            "kind": "canonical_extracted_text",
            "path": canonical.relative_to(osii_root).as_posix(),
            "text": canonical.read_text(encoding="utf-8"),
            "extraction_id": (list_extraction_variants(osii_root, file_id) or {}).get("primary_id"),
        }

    return None
