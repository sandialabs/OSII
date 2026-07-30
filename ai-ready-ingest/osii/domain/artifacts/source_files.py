from __future__ import annotations

from pathlib import Path

from osii.domain.read.docs import get_doc_meta


def _existing_file_within(root: Path, relative_path: str) -> Path | None:
    root = root.resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if candidate.exists() and candidate.is_file():
        return candidate
    return None


def _resolve_from_root(root: Path, source_relpath: str) -> Path | None:
    """Resolve both root-relative and data-volume-relative source paths."""
    normalized_root = root.resolve()
    root_prefix = f"{normalized_root.name}/"

    # Processing records paths relative to the parent data volume, so a file
    # under `/data/source` is normally stored as `source/path/to/file.pdf`.
    if source_relpath.startswith(root_prefix):
        candidate = _existing_file_within(
            normalized_root,
            source_relpath[len(root_prefix) :],
        )
        if candidate is not None:
            return candidate

    # Preserve compatibility with stores that recorded paths directly
    # relative to the configured source or upload root.
    return _existing_file_within(normalized_root, source_relpath)


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

    candidate_shared = _resolve_from_root(shared_volume_root, source_relpath)
    if candidate_shared is not None:
        return candidate_shared

    candidate_upload = _resolve_from_root(upload_root, source_relpath)
    if candidate_upload is not None:
        return candidate_upload

    return None
