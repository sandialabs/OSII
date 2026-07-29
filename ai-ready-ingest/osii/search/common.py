from pathlib import Path
import json

import faiss
import numpy as np
from osii.model_clients import create_embedding_client

from osii.indexing.common import (
    embeddings_index_path,
    embeddings_mapping_path,
    get_embedding_model,
)


def load_faiss_index(osii_root: Path):
    path = embeddings_index_path(osii_root)
    if not path.exists():
        raise RuntimeError(f"FAISS index not found: {path}")
    return faiss.read_index(str(path))


def load_mapping(osii_root: Path) -> list[dict]:
    path = embeddings_mapping_path(osii_root)
    if not path.exists():
        raise RuntimeError(f"Embeddings mapping not found: {path}")

    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def embed_query(text: str, model: str | None = None) -> np.ndarray:
    client = create_embedding_client()
    model_name = get_embedding_model(model)

    vec = np.array([client.embed(model=model_name, texts=[text])[0]], dtype="float32")
    faiss.normalize_L2(vec)
    return vec


def search_segments(osii_root: Path, query: str, top_k: int = 10, model: str | None = None) -> list[dict]:
    index = load_faiss_index(osii_root)
    mapping = load_mapping(osii_root)

    q = embed_query(query, model=model)
    scores, ids = index.search(q, top_k)

    results = []
    for score, idx in zip(scores[0], ids[0]):
        if idx < 0:
            continue
        if idx >= len(mapping):
            continue

        row = mapping[idx].copy()
        row["score"] = float(score)
        results.append(row)

    return results
