"""Filesystem adapter for bounded, rebuildable topic geometry caches."""

from __future__ import annotations
import json
from pathlib import Path
from osii.domain.services import topics
from osii.domain.read.catalog import load_files_catalog
from osii.domain.scopes.membership import list_scope_file_ids
from osii.domain.artifacts.artifact_staleness import get_artifact_staleness
from osii.domain.storage.atomic import atomic_write_text
from osii.indexing.common import (
    embedding_namespace,
    embeddings_index_path,
    embeddings_mapping_path,
    embeddings_meta_path,
)
from osii.domain.topic_cache import topic_cache_key, hydrate_topic_map, pack_topic_map
from osii.domain.read.synthesis import get_suggested_metadata


def labels(osii_root: Path, document: dict) -> dict:
    result = {
        **document,
        "filename": Path(document["source_relpath"]).name,
        "media_type": document.get("media_type", document.get("mime", "")),
    }
    result.update(get_suggested_metadata(osii_root, document["file_id"]))
    return result


def context(osii_root: Path, scope: dict, limit: int | None) -> tuple[str, list[dict]]:
    catalog = {doc["file_id"]: doc for doc in load_files_catalog(osii_root)}
    members = set(list_scope_file_ids(osii_root, scope)) & catalog.keys()
    documents = [labels(osii_root, catalog[fid]) for fid in sorted(members)]
    try:
        paths = [
            fn(osii_root)
            for fn in (
                embeddings_index_path,
                embeddings_mapping_path,
                embeddings_meta_path,
            )
        ]
        signatures = [
            (str(path.resolve()), path.stat().st_size, path.stat().st_mtime_ns)
            for path in paths
        ]
        if (
            signatures[0][1] > topics.MAX_INDEX_BYTES
            or signatures[1][1] > topics.MAX_MAPPING_BYTES
        ):
            raise topics.TopicIndexUnavailable(
                "This index exceeds the explorer's vector / mapping limits."
            )
        stale = sorted(
            fid
            for fid in members
            if (get_artifact_staleness(osii_root, fid) or {})
            .get("stale", {})
            .get("embeddings")
        )
    except (OSError, ValueError) as exc:
        if isinstance(exc, topics.TopicIndexUnavailable):
            raise
        raise topics.TopicIndexUnavailable(
            "No readable index exists. Build embeddings in Intake, then refresh."
        ) from exc
    key = topic_cache_key([embedding_namespace(), signatures, stale], documents, limit)
    return key, documents


def topic_map(osii_root: Path, scope: dict, limit: int | None = None) -> dict:
    key, documents = context(osii_root, scope, limit)
    directory = osii_root / "cache" / "topics"
    path = directory / (key + ".json")
    try:
        cached = (
            json.loads(path.read_text(encoding="utf-8"))
            if path.stat().st_size < 32_000_000
            else None
        )
    except (OSError, ValueError):
        cached = None
    hit = hydrate_topic_map(cached, documents)
    if hit is not None:
        return hit
    result = topics.topic_map(osii_root, scope, limit)
    after, documents = context(osii_root, scope, limit)
    if after != key:
        raise topics.TopicIndexUnavailable(
            "The index or scope changed. Refresh the map after indexing completes."
        )
    packed = pack_topic_map(result)
    try:
        atomic_write_text(path, json.dumps(packed, allow_nan=False))
        # Only remove files owned by this cache, never canonical storage.
        owned = [
            p
            for p in directory.glob("*.json")
            if len(p.stem) == 64 and all(c in "0123456789abcdef" for c in p.stem)
        ]
        for old in sorted(owned, key=lambda p: p.stat().st_mtime_ns, reverse=True)[16:]:
            old.unlink(missing_ok=True)
    except OSError:
        pass  # Read-only stores can still explore without persistence.
    return hydrate_topic_map(packed, documents) or result


def related_documents(
    osii_root: Path, scope: dict, file_id: str, limit: int = 12
) -> dict:
    result = topics.related_documents(osii_root, scope, file_id, limit)
    result["document"] = labels(osii_root, result["document"])
    result["results"] = [labels(osii_root, doc) for doc in result["results"]]
    return result
