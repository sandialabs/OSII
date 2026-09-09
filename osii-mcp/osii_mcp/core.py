"""Core traversal logic for OSII MCP.

This file contains pure Python helper functions that call the installed `osii`
package directly. The MCP server in `main.py` simply exposes these as tools.
"""

from pathlib import Path
from typing import Any

from osii.domain.artifacts.object_summaries import get_object_summaries
from osii.domain.artifacts.scope_artifacts import get_scope_artifact_summary
from osii.domain.artifacts.text_spans import get_text_context_by_span
from osii.domain.read.catalog import load_folders_catalog
from osii.domain.scopes.collections import (
    get_collection,
    list_collection_documents,
    list_collections,
)
from osii.domain.scopes.descriptors import describe_scope
from osii.domain.scopes.membership import list_scope_file_ids
from osii.domain.scopes.summaries import get_scope_object_summaries
from osii.domain.services.search import dashboard_search
from osii.api.objects_routes import get_object  # not ideal to call route layer
from osii.domain.read.docs import get_doc_meta, get_doc_overview
from osii.domain.artifacts.object_artifacts import get_object_artifact_summary
from osii.domain.artifacts.object_processing import get_object_processing_metadata
from osii.domain.artifacts.read_enrichments import (
    get_scope_enrichment_payload,
    list_scope_enrichments,
)
from osii.domain.artifacts.text_representations import get_preferred_text_representation


def _osii_root() -> Path:
    import os

    value = os.getenv("OSII_ROOT")
    if not value:
        raise RuntimeError("OSII_ROOT environment variable is not set.")
    path = Path(value).resolve()
    if not path.exists():
        raise RuntimeError(f"OSII_ROOT does not exist: {path}")
    return path


def get_root_scope() -> dict[str, Any]:
    osii_root = _osii_root()
    scope = {"scope_type": "root"}
    return {
        "scope": describe_scope(osii_root, scope),
        "member_file_ids": list_scope_file_ids(osii_root, scope),
    }


def list_folder_scopes() -> dict[str, Any]:
    osii_root = _osii_root()
    folders = load_folders_catalog(osii_root)
    return {
        "scopes": [
            {
                "scope_type": "folder",
                "scope_id": entry.get("folder_id"),
                "folder_id": entry.get("folder_id"),
                "path": entry.get("path") or "",
                "label": (entry.get("path") or "").strip("/") or "root-folder",
            }
            for entry in folders
            if entry.get("folder_id")
        ]
    }


def list_collection_scopes() -> dict[str, Any]:
    osii_root = _osii_root()
    collections = list_collections(osii_root)
    return {
        "scopes": [
            {
                "scope_type": "collection",
                "scope_id": item["id"],
                "collection_id": item["id"],
                "label": item["name"],
                "kind": item.get("kind", "manual"),
                "description": item.get("description"),
                "document_count": item.get("document_count", 0),
            }
            for item in collections
        ]
    }


def describe_scope_core(scope: dict[str, Any]) -> dict[str, Any]:
    osii_root = _osii_root()
    return {
        "scope": describe_scope(osii_root, scope),
        "member_file_ids": list_scope_file_ids(osii_root, scope),
    }


def get_scope_summaries(scope: dict[str, Any]) -> dict[str, Any]:
    osii_root = _osii_root()
    return get_scope_object_summaries(osii_root, scope)


def get_scope_artifacts(scope: dict[str, Any]) -> dict[str, Any]:
    osii_root = _osii_root()
    return get_scope_artifact_summary(osii_root, scope)


def list_enrichment_artifacts(scope: dict[str, Any]) -> dict[str, Any]:
    osii_root = _osii_root()
    return {
        "scope": scope,
        "enrichments": list_scope_enrichments(osii_root, scope),
    }


def get_enrichment_artifact(scope: dict[str, Any], filename: str) -> dict[str, Any]:
    osii_root = _osii_root()
    result = get_scope_enrichment_payload(osii_root, scope, filename)
    if result is None:
        raise RuntimeError(f"Unknown enrichment artifact: {filename}")
    return result


def get_collection_core(collection_id: str) -> dict[str, Any]:
    osii_root = _osii_root()
    collection = get_collection(osii_root, collection_id)
    if collection is None:
        raise RuntimeError(f"Unknown collection_id: {collection_id}")
    return {
        "collection": collection,
        "file_ids": list_collection_documents(osii_root, collection_id),
    }


def get_object_core(file_id: str) -> dict[str, Any]:
    osii_root = _osii_root()

    meta = get_doc_meta(osii_root, file_id)
    if meta is None:
        raise RuntimeError(f"Unknown file_id: {file_id}")

    overview = get_doc_overview(osii_root, file_id)
    processing = get_object_processing_metadata(osii_root, file_id)
    enrichments = list_scope_enrichments(
        osii_root,
        {"scope_type": "object", "file_id": file_id},
    )
    artifact_summary = get_object_artifact_summary(osii_root, file_id)

    return {
        "file_id": file_id,
        "meta": meta,
        "overview": overview,
        "processing": processing,
        "enrichments": enrichments,
        "artifact_summary": artifact_summary,
    }


def get_object_preferred_text(file_id: str) -> dict[str, Any]:
    osii_root = _osii_root()
    result = get_preferred_text_representation(osii_root, file_id)
    if result is None:
        raise RuntimeError(f"Unknown file_id or text not found: {file_id}")
    return {
        "file_id": file_id,
        "representation": result["name"],
        "kind": result["kind"],
        "text": result["text"],
        "path": result["path"],
    }


def get_object_text_span_context(file_id: str, char_start: int, char_end: int, context_chars: int = 200) -> dict[str, Any]:
    osii_root = _osii_root()
    result = get_text_context_by_span(
        osii_root,
        file_id,
        char_start=char_start,
        char_end=char_end,
        context_chars=context_chars,
    )
    if result is None:
        raise RuntimeError(f"Could not resolve text span context for file_id={file_id}")
    return result


def search_scope(query: str, scope: dict[str, Any], mode: str = "hybrid", top_k: int = 10, group_by: str | None = "file") -> dict[str, Any]:
    osii_root = _osii_root()
    retrieval_mode_used, results = dashboard_search(
        osii_root,
        query=query,
        mode=mode,
        top_k=top_k,
        scope=scope,
        group_by=group_by,
    )
    return {
        "query": query,
        "mode": mode,
        "retrieval_mode_used": retrieval_mode_used,
        "top_k": top_k,
        "scope": scope,
        "group_by": group_by,
        "results": results,
    }
