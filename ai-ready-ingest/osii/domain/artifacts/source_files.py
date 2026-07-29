from __future__ import annotations

from pathlib import Path

from osii.domain.read.docs import get_doc_meta


def get_source_file_path(
    osii_root: Path,
    shared_volume_root: Path,
    upload_root: Path,
    file_id: str,
) -> Path | None:
    meta = get_doc_meta(osii_root, file_id)
    if meta is None:
        return None

    source_relpath = (meta.get("file", {}) or {}).get("source_relpath")
    if not source_relpath:
        return None

    source_relpath = str(source_relpath).replace("\\", "/").strip("/")

    candidate_shared = (shared_volume_root / source_relpath).resolve()
    if candidate_shared.exists() and candidate_shared.is_file():
        return candidate_shared

    candidate_upload = (upload_root / source_relpath).resolve()
    if candidate_upload.exists() and candidate_upload.is_file():
        return candidate_upload

    return None