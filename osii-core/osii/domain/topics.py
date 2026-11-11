"""Read-only exploration over a single model's canonical PostgreSQL vectors.

PCA projection is shared with OSII-local. No model calls or persistence here.
"""
import hashlib
from collections.abc import Iterable, Mapping
from typing import Any
import numpy as np


from osii.domain.document_metadata import document_labels, synthesis_labels
from osii.domain.topic_projection import MAX_DOCUMENT_VECTOR_BYTES, TopicIndexUnavailable, project_documents


def document_space(documents: list[dict], rows: Iterable[Mapping[str, Any]], model: str, revision: int) -> tuple[list[dict], np.ndarray, dict, int]:
    if not model:
        raise TopicIndexUnavailable("An administrator must select an embedding model and a curator must process the dataset first.")
    sums, counts, dimensions = {}, {}, None
    stale = set()
    for row in rows:
        values = row.get("embedding")
        if not values:
            continue
        if row.get("embedding_model") != model:
            stale.add(row["file_id"])
            continue
        vector = np.asarray(values, dtype=np.float32)
        if vector.ndim != 1 or not 1 <= len(vector) <= 8192 or not np.isfinite(vector).all():
            raise TopicIndexUnavailable("Invalid indexed vectors. Reprocess embeddings before exploring.")
        dimensions = dimensions or len(vector)
        if len(vector) != dimensions:
            raise TopicIndexUnavailable("Embedding dimensions disagree. Reprocess using one consistent model.")
        if (len(sums) + (row["file_id"] not in sums))*dimensions*4 > MAX_DOCUMENT_VECTOR_BYTES:
            raise TopicIndexUnavailable("Choose a smaller scope; document vectors exceed the 64 MiB exploration limit.")
        norm = np.linalg.norm(vector)
        if norm <= 1e-12:
            continue
        fid = row["file_id"]
        sums.setdefault(fid, np.zeros(dimensions, dtype=np.float32))[:] += vector/norm
        counts[fid] = counts.get(fid, 0)+1
    indexed, vectors = [], []
    for doc in sorted(documents, key=lambda d: d["file_id"]):
        fid = doc["file_id"]
        if fid not in sums or np.linalg.norm(sums[fid]) <= 1e-12:
            continue
        indexed.append({**document_labels(doc), **synthesis_labels(doc), "chunk_count": counts[fid]})
        vectors.append(sums[fid]/np.linalg.norm(sums[fid]))
    stale -= {d["file_id"] for d in indexed}
    index = {"id":hashlib.sha256(f"{revision}:{model}:{dimensions}".encode()).hexdigest()[:20],
        "provider":"configured", "model":model, "dimensions":dimensions or 0, "semantic":True, "created_utc":None}
    return indexed, np.array(vectors, dtype=np.float32).reshape(len(vectors), dimensions or 0), index, len(stale)


def topic_map(documents: list[dict], rows: Iterable[Mapping[str, Any]], model: str, revision: int, limit: int | None = None) -> dict:
    docs, vectors, index, stale = document_space(documents, rows, model, revision)
    coordinates, variance = project_documents(vectors)
    return {"index":index,"scope_count":len(documents),"indexed_count":len(docs),"stale_count":stale,
        "unindexed_count":len(documents)-len(docs)-stale,"shown_count":len(docs[:limit]),
        "projection":"pca","explained_variance":variance,
        "points":[dict(doc,x=float(point[0]),y=float(point[1])) for doc,point in zip(docs[:limit],coordinates)]}


def related_documents(documents: list[dict], rows: Iterable[Mapping[str, Any]], model: str, revision: int, file_id: str, limit: int = 12) -> dict:
    docs,vectors,index,_ = document_space(documents,rows,model,revision)
    ids = [d["file_id"] for d in docs]
    if file_id not in ids:
        raise TopicIndexUnavailable("This document has no compatible embeddings in the selected scope.")
    chosen = ids.index(file_id)
    scores = vectors @ vectors[chosen]
    order = sorted((i for i in range(len(ids)) if i != chosen),key=lambda i:(-scores[i],ids[i]))[:limit]
    return {"index":index,"document":docs[chosen],"results":[dict(docs[i],similarity=float(np.clip(scores[i],-1,1))) for i in order]}
