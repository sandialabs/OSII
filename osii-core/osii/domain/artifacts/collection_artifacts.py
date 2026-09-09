from __future__ import annotations

from pathlib import Path

from osii.domain.artifacts.read_enrichments import list_scope_enrichments
from osii.domain.read.catalog import load_files_catalog
from osii.domain.scopes.collections import get_collection, list_collection_documents
from osii.domain.storage.store import collection_syntheses_dir


def list_collection_syntheses(osii_root: Path, collection_id: str) -> list[dict]:
    path = collection_syntheses_dir(osii_root, collection_id)
    if not path.exists():
        return []

    items = []
    for child in sorted(path.iterdir(), key=lambda p: p.name.lower()):
        if child.is_file():
            items.append(
                {
                    "name": child.name,
                    "relpath": f"collections/{collection_id}/syntheses/{child.name}",
                }
            )
    return items


def get_collection_artifact_summary(osii_root: Path, collection_id: str) -> dict | None:
    collection = get_collection(osii_root, collection_id)
    if collection is None:
        return None

    file_ids = list_collection_documents(osii_root, collection_id)
    syntheses = list_collection_syntheses(osii_root, collection_id)
    enrichments = list_scope_enrichments(
        osii_root,
        {"scope_type": "collection", "collection_id": collection_id},
    )

    return {
        "collection_id": collection_id,
        "artifacts": {
            "member_count": len(file_ids),
            "has_synthesis": len(syntheses) > 0,
            "has_enrichments": len(enrichments) > 0,
            "syntheses": syntheses,
            "enrichments": enrichments,
        },
        "actions": {
            "can_synthesize": len(file_ids) > 0,
            "can_enrich": len(file_ids) > 0,
        },
    }