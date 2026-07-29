from __future__ import annotations

from pathlib import Path

from osii.domain.processing.source_status import get_source_status
from osii.domain.read.docs import get_doc_meta


def get_object_source_state(osii_root: Path, file_id: str) -> dict | None:
    meta = get_doc_meta(osii_root, file_id)
    if meta is None:
        return None

    status_doc = get_source_status(osii_root, file_id)
    source_status = (status_doc or {}).get("source_status", {})

    return {
        "file_id": file_id,
        "status": source_status.get("status", "active"),
        "source_relpath": source_status.get("source_relpath") or meta.get("file", {}).get("source_relpath"),
    }