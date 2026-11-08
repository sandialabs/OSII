"""Read-only document exploration in one provider/model embedding space."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import tomllib

import faiss
import numpy as np

from osii.domain.storage.store import provenance_path
from osii.domain.topic_projection import TopicIndexUnavailable, project_documents

from osii.domain.artifacts.artifact_staleness import get_artifact_staleness
from osii.domain.read.catalog import load_files_catalog
from osii.domain.scopes.membership import list_scope_file_ids
from osii.indexing.common import embedding_namespace


MAX_INDEX_BYTES = 1024 * 1024 * 1024
MAX_MAPPING_BYTES = 512 * 1024 * 1024
MAX_INDEX_CHUNKS = 1_000_000


@dataclass
class DocumentSpace:
    documents: list[dict]
    vectors: np.ndarray
    index: dict
    scope_count: int
    stale_count: int


def load_document_space(osii_root: Path, scope: dict) -> DocumentSpace:
    catalog = {row["file_id"]: row for row in load_files_catalog(osii_root)}
    members = set(list_scope_file_ids(osii_root, scope)) & catalog.keys()
    if len(members) > 5000:
        raise TopicIndexUnavailable("Choose a folder or collection with at most 5,000 documents.")
    provider, model = embedding_namespace()
    directory = osii_root / "embeddings" / "providers" / provider / model
    paths = [directory / name for name in ("segments.faiss", "segments.mapping.jsonl", "segments.meta.toml")]

    def signature():
        return [(path.stat().st_size, path.stat().st_mtime_ns) for path in paths]

    try:
        before = signature()
        if before[0][0] > MAX_INDEX_BYTES or before[1][0] > MAX_MAPPING_BYTES:
            raise TopicIndexUnavailable("This index exceeds the explorer's 1 GiB vector / 512 MiB mapping limits.")
        meta = tomllib.loads(paths[2].read_text(encoding="utf-8"))["embeddings"]
        index = faiss.read_index(str(paths[0]))
        if not isinstance(index, faiss.IndexFlatIP) or index.ntotal > MAX_INDEX_CHUNKS or not 1 <= index.d <= 8192:
            raise TopicIndexUnavailable("The explorer requires a flat inner-product index with at most 1,000,000 chunks and 8,192 dimensions.")
        if index.d != meta["dimension"] or index.ntotal != meta["count"]:
            raise TopicIndexUnavailable("The embedding index and metadata disagree. Rebuild embeddings in Intake.")
        if len(members) * index.d * 8 > 64 * 1024 * 1024:
            raise TopicIndexUnavailable("This scope exceeds the 64 MiB document-vector limit. Choose a smaller folder or collection.")
        stale = {file_id for file_id in members if (get_artifact_staleness(osii_root, file_id) or {}).get("stale", {}).get("embeddings")}
        eligible = members - stale
        sums: dict[str, np.ndarray] = {}
        counts: dict[str, int] = {}
        row_count = 0
        with paths[1].open(encoding="utf-8") as mapping:
            for ordinal, line in enumerate(mapping):
                row = json.loads(line)
                if ordinal >= index.ntotal or row.get("faiss_id", ordinal) != ordinal or not isinstance(row.get("file_id"), str):
                    raise TopicIndexUnavailable("The embedding mapping is inconsistent. Rebuild embeddings in Intake.")
                row_count += 1
                file_id = row["file_id"]
                if file_id not in eligible:
                    continue
                vector = index.reconstruct(ordinal).astype(np.float64)
                norm = np.linalg.norm(vector)
                if not np.isfinite(vector).all() or norm <= 1e-12:
                    raise TopicIndexUnavailable("The index contains invalid vectors. Rebuild embeddings in Intake.")
                sums.setdefault(file_id, np.zeros(index.d, dtype=np.float64))[:] += vector / norm
                counts[file_id] = counts.get(file_id, 0) + 1
        if row_count != index.ntotal or signature() != before:
            raise TopicIndexUnavailable("The index changed or its mapping is incomplete. Wait for indexing to finish, then refresh.")
        documents, vectors = [], []
        for file_id in sorted(sums):
            norm = np.linalg.norm(sums[file_id])
            if norm <= 1e-12:
                continue
            row = catalog[file_id]
            title = {}
            try:
                provenance = tomllib.loads(provenance_path(osii_root, file_id).read_text(encoding='utf-8'))
                config = provenance.get('synthesis', {}).get('config', {})
                if not (get_artifact_staleness(osii_root, file_id) or {}).get('stale', {}).get('syntheses'):
                    title = {k: config[k] for k in ('document_title','title_method') if config.get(k)}
            except (OSError, ValueError, TypeError):
                pass
            documents.append({
                "file_id": file_id,
                "filename": Path(row["source_relpath"]).name,
                "source_relpath": row["source_relpath"],
                "chunk_count": counts[file_id], **title,
            })
            vectors.append(sums[file_id] / norm)
        identity = hashlib.sha256(repr((provider, model, before)).encode()).hexdigest()[:20]
        return DocumentSpace(
            documents, np.array(vectors).reshape(len(vectors), index.d),
            {"id": identity, "provider": str(meta.get("provider_id") or meta.get("provider") or provider),
             "model": str(meta.get("model") or model), "dimensions": index.d,
             "semantic": meta.get("semantic") is True and provider != "local.hashing",
             "created_utc": str(meta["created_utc"]) if meta.get("created_utc") is not None else None},
            len(members), len(stale),
        )
    except TopicIndexUnavailable:
        raise
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, AttributeError) as exc:
        raise TopicIndexUnavailable("No readable, complete index exists for the selected embedding model. Build embeddings in Intake, then refresh.") from exc


def topic_map(osii_root: Path, scope: dict, limit: int = 500) -> dict:
    space = load_document_space(osii_root, scope)
    # Stable, explicitly disclosed subset; related-document ranking uses all members.
    documents = space.documents[:limit]
    coordinates, variance = project_documents(space.vectors[:limit])
    return {
        "index": space.index, "scope_count": space.scope_count,
        "indexed_count": len(space.documents), "stale_count": space.stale_count,
        "unindexed_count": space.scope_count - len(space.documents) - space.stale_count,
        "shown_count": len(documents), "projection": "pca", "explained_variance": variance,
        "points": [dict(document, x=float(point[0]), y=float(point[1])) for document, point in zip(documents, coordinates)],
    }


def related_documents(osii_root: Path, scope: dict, file_id: str, limit: int = 12) -> dict:
    space = load_document_space(osii_root, scope)
    ids = [document["file_id"] for document in space.documents]
    if file_id not in ids:
        raise TopicIndexUnavailable("This document has no current embeddings in the selected scope. Choose another document or rebuild embeddings.")
    selected = ids.index(file_id)
    similarities = space.vectors @ space.vectors[selected]
    order = sorted((i for i in range(len(ids)) if i != selected), key=lambda i: (-similarities[i], ids[i]))[:limit]
    return {"index": space.index, "document": space.documents[selected],
            "results": [dict(space.documents[i], similarity=float(np.clip(similarities[i], -1, 1))) for i in order]}
