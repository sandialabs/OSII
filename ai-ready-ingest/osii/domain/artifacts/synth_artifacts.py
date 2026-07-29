from __future__ import annotations

from pathlib import Path
import json

from osii.domain.storage.store import (
    collection_syntheses_dir,
    folder_syntheses_dir,
    object_syntheses_dir,
    root_syntheses_dir,
)


def _variant_basename(method: str) -> str:
    method = (method or "").strip()
    if not method:
        raise ValueError("method is required")
    return method.replace(" ", "_")


def write_object_synthesis_variant(
    osii_root: Path,
    file_id: str,
    *,
    method: str,
    text: str,
    metadata: dict | None = None,
) -> dict:
    base = _variant_basename(method)
    out_dir = object_syntheses_dir(osii_root, file_id)

    text_path = out_dir / f"{base}.txt"
    meta_path = out_dir / f"{base}.json"

    text_path.write_text(text, encoding="utf-8")
    meta_path.write_text(
        json.dumps(metadata or {}, indent=2),
        encoding="utf-8",
    )

    return {
        "scope_type": "object",
        "file_id": file_id,
        "method": method,
        "text_path": f"objects/{file_id}/syntheses/{text_path.name}",
        "metadata_path": f"objects/{file_id}/syntheses/{meta_path.name}",
    }


def write_image_synthesis_variant(
    osii_root: Path,
    file_id: str,
    image,
    *,
    method: str,
    text: str,
    metadata: dict | None = None,
) -> dict:
    base = _variant_basename(method)
    out_dir = object_syntheses_dir(osii_root, file_id)

    text_path = out_dir / f"{base}_{image.split('.')[0]}.txt"
    meta_path = out_dir / f"{base}_{image.split('.')[0]}.json"

    text_path.write_text(text, encoding="utf-8")
    meta_path.write_text(
        json.dumps(metadata or {}, indent=2),
        encoding="utf-8",
    )

    return {
        "scope_type": "object",
        "file_id": file_id,
        "method": method,
        "text_path": f"objects/{file_id}/syntheses/{text_path.name}",
        "metadata_path": f"objects/{file_id}/syntheses/{meta_path.name}",
    }


def write_folder_synthesis_variant(
    osii_root: Path,
    folder_id: str,
    *,
    method: str,
    text: str,
    metadata: dict | None = None,
) -> dict:
    base = _variant_basename(method)
    out_dir = folder_syntheses_dir(osii_root, folder_id)

    text_path = out_dir / f"{base}.txt"
    meta_path = out_dir / f"{base}.json"

    text_path.write_text(text, encoding="utf-8")
    meta_path.write_text(
        json.dumps(metadata or {}, indent=2),
        encoding="utf-8",
    )

    return {
        "scope_type": "folder",
        "folder_id": folder_id,
        "method": method,
        "text_path": f"folders/folder-{folder_id}.syntheses/{text_path.name}",
        "metadata_path": f"folders/folder-{folder_id}.syntheses/{meta_path.name}",
    }


def write_collection_synthesis_variant(
    osii_root: Path,
    collection_id: str,
    *,
    method: str,
    text: str,
    metadata: dict | None = None,
) -> dict:
    base = _variant_basename(method)
    out_dir = collection_syntheses_dir(osii_root, collection_id)

    text_path = out_dir / f"{base}.txt"
    meta_path = out_dir / f"{base}.json"

    text_path.write_text(text, encoding="utf-8")
    meta_path.write_text(
        json.dumps(metadata or {}, indent=2),
        encoding="utf-8",
    )

    return {
        "scope_type": "collection",
        "collection_id": collection_id,
        "method": method,
        "text_path": f"collections/{collection_id}/syntheses/{text_path.name}",
        "metadata_path": f"collections/{collection_id}/syntheses/{meta_path.name}",
    }


def write_root_synthesis_variant(
    osii_root: Path,
    *,
    method: str,
    text: str,
    metadata: dict | None = None,
) -> dict:
    base = _variant_basename(method)
    out_dir = root_syntheses_dir(osii_root)

    text_path = out_dir / f"{base}.txt"
    meta_path = out_dir / f"{base}.json"

    text_path.write_text(text, encoding="utf-8")
    meta_path.write_text(
        json.dumps(metadata or {}, indent=2),
        encoding="utf-8",
    )

    return {
        "scope_type": "root",
        "scope_id": "root",
        "method": method,
        "text_path": f"syntheses/{text_path.name}",
        "metadata_path": f"syntheses/{meta_path.name}",
    }