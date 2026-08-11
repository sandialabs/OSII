from __future__ import annotations

import json
import pickle
import re
from pathlib import Path

import bm25s

from osii.domain.storage.store import (
    embeddings_chunks_manifest_path,
    embeddings_lexical_index_path,
    embeddings_lexical_meta_path,
)
from osii.indexing.chunking import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_CHUNKING_METHOD,
    write_chunk_manifest,
)


TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,}")


def tokenize(text: str) -> list[str]:
    return [tok.lower() for tok in TOKEN_RE.findall(text or "")]


def ensure_chunk_manifest(
    osii_root: Path,
    *,
    method: str = DEFAULT_CHUNKING_METHOD,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> Path:
    path = embeddings_chunks_manifest_path(osii_root)
    write_chunk_manifest(
        osii_root,
        method=method,
        chunk_size=chunk_size,
        overlap=overlap,
    )
    return path


def load_chunk_manifest(osii_root: Path) -> list[dict]:
    path = embeddings_chunks_manifest_path(osii_root)
    if not path.exists():
        path = ensure_chunk_manifest(osii_root)

    if not path.exists():
        raise RuntimeError(f"Chunk manifest not found: {path}")

    rows = []
    bad_lines = []

    for line_num, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        raw = line.strip()
        if not raw:
            continue

        try:
            rows.append(json.loads(raw))
        except Exception as exc:
            bad_lines.append((line_num, str(exc), raw[:300]))

    if bad_lines:
        print("WARNING: malformed chunk manifest lines detected and skipped:")
        for line_num, err, preview in bad_lines[:10]:
            print(f"  line {line_num}: {err}")
            print(f"    preview: {preview}")
        if len(bad_lines) > 10:
            print(f"  ... and {len(bad_lines) - 10} more")

    if not rows:
        raise RuntimeError(f"No valid chunk rows found in chunk manifest: {path}")

    return rows


def build_bm25_index(osii_root: Path) -> tuple[Path, Path]:
    rows = load_chunk_manifest(osii_root)

    corpus_tokens = [tokenize(row.get("text", "")) for row in rows]
    retriever = bm25s.BM25()
    retriever.index(corpus_tokens)

    index_path = embeddings_lexical_index_path(osii_root)
    meta_path = embeddings_lexical_meta_path(osii_root)
    index_path.parent.mkdir(parents=True, exist_ok=True)

    with index_path.open("wb") as f:
        pickle.dump(
            {
                "retriever": retriever,
                "rows": rows,
            },
            f,
        )

    meta_path.write_text(
        json.dumps(
            {
                "chunk_manifest_path": str(embeddings_chunks_manifest_path(osii_root)),
                "document_count": len(rows),
                "tokenizer": "simple_regex_lower",
                "index_type": "bm25s",
                "chunking": {
                    "method": rows[0].get("chunk_method") if rows else None,
                    "chunk_size": rows[0].get("chunk_size") if rows else None,
                    "chunk_overlap": rows[0].get("chunk_overlap") if rows else None,
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    return index_path, meta_path


def load_bm25_index(osii_root: Path):
    index_path = embeddings_lexical_index_path(osii_root)

    if not index_path.exists():
        build_bm25_index(osii_root)

    with index_path.open("rb") as f:
        payload = pickle.load(f)

    return payload["retriever"], payload["rows"]


def lexical_search_chunks(osii_root: Path, query: str, top_k: int = 10) -> list[dict]:
    retriever, rows = load_bm25_index(osii_root)

    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    if not rows:
        return []

    k = min(int(top_k), len(rows))
    if k <= 0:
        return []

    scores, doc_ids = retriever.retrieve([query_tokens], k=k)

    results = []
    for score, idx in zip(scores[0], doc_ids[0]):
        if idx is None:
            continue
        idx = int(idx)
        if idx < 0 or idx >= len(rows):
            continue

        row = rows[idx].copy()
        row["score"] = float(score)
        results.append(row)

    return results
