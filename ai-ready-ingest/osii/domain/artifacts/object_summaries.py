from __future__ import annotations

from pathlib import Path

from osii.domain.artifacts.object_artifacts import get_object_artifact_summary
from osii.domain.artifacts.object_processing import get_object_processing_metadata
from osii.domain.artifacts.text_representations import list_text_representations
from osii.domain.read.docs import get_doc_meta
from osii.domain.read.synthesis import get_synth_text
from osii.domain.scopes.collections import list_collections_for_file


def _preferred_text_info(osii_root: Path, file_id: str) -> tuple[bool, str | None]:
    reps = list_text_representations(osii_root, file_id) or []
    for rep in reps:
        if rep.get("preferred"):
            return True, rep.get("kind")
    return False, None


def get_object_summary(osii_root: Path, file_id: str) -> dict | None:
    meta = get_doc_meta(osii_root, file_id)
    if meta is None:
        return None

    file_meta = meta.get("file", {})
    processing = get_object_processing_metadata(osii_root, file_id)
    artifact_summary = get_object_artifact_summary(osii_root, file_id)
    synth = get_synth_text(osii_root, file_id)

    has_preferred_text, preferred_text_kind = _preferred_text_info(osii_root, file_id)

    synthesis_preview = None
    if synth:
        synthesis_preview = synth[:240].strip()

    mime = file_meta.get("mime")
    preview_available = mime == "application/pdf"

    return {
        "file_id": file_id,
        "filename": file_meta.get("filename"),
        "source_relpath": file_meta.get("source_relpath"),
        "source_file_relpath": file_meta.get("source_relpath"),
        "mime": mime,
        "collections": list_collections_for_file(osii_root, file_id),
        "processing": processing,
        "source_state": (artifact_summary or {}).get("source_state"),
        "has_preferred_text": has_preferred_text,
        "preferred_text_kind": preferred_text_kind,
        "has_synthesis": (artifact_summary or {}).get("artifacts", {}).get("has_synthesis", False),
        "has_enrichments": (artifact_summary or {}).get("artifacts", {}).get("has_enrichments", False),
        "synthesis_preview": synthesis_preview,
        "preview_available": preview_available,
    }


def get_object_summaries(osii_root: Path, file_ids: list[str]) -> list[dict]:
    results = []
    for file_id in file_ids:
        item = get_object_summary(osii_root, file_id)
        if item is not None:
            results.append(item)
    return results