from __future__ import annotations

from pathlib import Path

from osii.domain.read.docs import get_doc_meta
from osii.domain.read.manifest import list_manifest_records
from osii.domain.read.synthesis import list_syntheses
from osii.domain.artifacts.read_enrichments import list_scope_enrichments
from osii.domain.artifacts.text_representations import list_text_representations


def get_object_artifact_summary(osii_root: Path, file_id: str) -> dict | None:
    meta = get_doc_meta(osii_root, file_id)
    if meta is None:
        return None

    manifest = list_manifest_records(osii_root, file_id)
    text_representations = list_text_representations(osii_root, file_id) or []
    syntheses = list_syntheses(osii_root, file_id)
    enrichments = list_scope_enrichments(osii_root, {"scope_type": "object", "file_id": file_id})

    has_extraction = len(manifest) > 0
    has_synthesis = len(syntheses) > 0
    has_enrichments = len(enrichments) > 0

    return {
        "file_id": file_id,
        "artifacts": {
            "has_extraction": has_extraction,
            "has_synthesis": has_synthesis,
            "has_enrichments": has_enrichments,
            "manifest_record_count": len(manifest),
            "text_representations": text_representations,
            "syntheses": syntheses,
            "enrichments": enrichments,
        },
        "actions": {
            "can_extract": True,
            "can_synthesize": has_extraction,
            "can_enrich": has_extraction,
        },
    }