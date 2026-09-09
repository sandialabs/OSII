from __future__ import annotations

from pathlib import Path

from osii.domain.artifacts.collection_artifacts import (
    get_collection_artifact_summary,
    list_collection_syntheses,
)
from osii.domain.artifacts.read_enrichments import list_scope_enrichments
from osii.domain.read.folder_synthesis import get_folder_synthesis_text
from osii.domain.read.folders import get_folder_manifest
from osii.domain.read.root import get_root_synth_text
from osii.domain.scopes.descriptors import describe_scope
from osii.domain.scopes.membership import list_scope_file_ids
from osii.domain.scopes.scopes import normalize_scope_type
from osii.domain.storage.store import root_syntheses_dir


def list_root_syntheses(osii_root: Path) -> list[dict]:
    path = root_syntheses_dir(osii_root)
    if not path.exists():
        return []

    items = []
    for child in sorted(path.iterdir(), key=lambda p: p.name.lower()):
        if child.is_file():
            items.append(
                {
                    "name": child.name,
                    "relpath": f"syntheses/{child.name}",
                }
            )
    return items


def _folder_scope_artifacts(osii_root: Path, scope: dict) -> dict:
    folder_id = scope["folder_id"]
    scope_desc = describe_scope(osii_root, scope)
    member_file_ids = list_scope_file_ids(osii_root, scope)

    synth_text = get_folder_synthesis_text(osii_root, folder_id)
    syntheses = []

    if synth_text is not None:
        syntheses.append(
            {
                "name": "current",
                "relpath": f"folders/folder-{folder_id}.synth.txt",
            }
        )

    enrichments = list_scope_enrichments(osii_root, scope)

    return {
        "scope": scope_desc,
        "artifact_summary": {
            "member_count": len(member_file_ids),
            "has_synthesis": synth_text is not None,
            "synthesis_preview": synth_text[:240].strip() if synth_text else None,
            "syntheses": syntheses,
            "has_enrichments": len(enrichments) > 0,
            "enrichments": enrichments,
        },
        "actions": {
            "can_synthesize": len(member_file_ids) > 0,
            "can_enrich": len(member_file_ids) > 0,
        },
    }


def _collection_scope_artifacts(osii_root: Path, scope: dict) -> dict:
    collection_id = scope["collection_id"]
    scope_desc = describe_scope(osii_root, scope)

    collection_summary = get_collection_artifact_summary(osii_root, collection_id)
    enrichments = list_scope_enrichments(osii_root, scope)
    syntheses = list_collection_syntheses(osii_root, collection_id)

    synthesis_preview = None
    if syntheses:
        synthesis_preview = syntheses[0]["name"]

    return {
        "scope": scope_desc,
        "artifact_summary": {
            "member_count": collection_summary["artifacts"]["member_count"] if collection_summary else 0,
            "has_synthesis": len(syntheses) > 0,
            "synthesis_preview": synthesis_preview,
            "syntheses": syntheses,
            "has_enrichments": len(enrichments) > 0,
            "enrichments": enrichments,
        },
        "actions": {
            "can_synthesize": (collection_summary["actions"]["can_synthesize"] if collection_summary else False),
            "can_enrich": (collection_summary["actions"]["can_enrich"] if collection_summary else False),
        },
    }


def _root_scope_artifacts(osii_root: Path, scope: dict) -> dict:
    scope_desc = describe_scope(osii_root, scope)
    member_file_ids = list_scope_file_ids(osii_root, scope)

    synth_text = get_root_synth_text(osii_root)
    syntheses = list_root_syntheses(osii_root)
    enrichments = list_scope_enrichments(osii_root, scope)

    return {
        "scope": scope_desc,
        "artifact_summary": {
            "member_count": len(member_file_ids),
            "has_synthesis": synth_text is not None or len(syntheses) > 0,
            "synthesis_preview": synth_text[:240].strip() if synth_text else None,
            "syntheses": syntheses,
            "has_enrichments": len(enrichments) > 0,
            "enrichments": enrichments,
        },
        "actions": {
            "can_synthesize": len(member_file_ids) > 0,
            "can_enrich": len(member_file_ids) > 0,
        },
    }


def get_scope_artifact_summary(osii_root: Path, scope: dict) -> dict:
    scope_type = normalize_scope_type(scope.get("scope_type") or scope.get("type"))

    if scope_type == "folder":
        return _folder_scope_artifacts(osii_root, scope)

    if scope_type == "collection":
        return _collection_scope_artifacts(osii_root, scope)

    if scope_type == "root":
        return _root_scope_artifacts(osii_root, scope)

    raise ValueError(f"Unsupported scope type for scope artifact summary: {scope_type}")