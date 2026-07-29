from pathlib import Path
import json
import os
import shutil
import time

import faiss
import numpy as np
import tomli_w

from typing import Any

from osii.model_clients import create_shirty_client

from osii.domain.storage.store import (
    embeddings_chunks_manifest_path,
    embeddings_dir as osii_embeddings_dir,
)
from osii.indexing.chunking import write_chunk_manifest
from osii.search.lexical import build_bm25_index


DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
APPROX_CHARS_PER_TOKEN = 4

MODEL_TOKEN_LIMITS = {
    "sentence-transformers/all-MiniLM-L6-v2": 256,
    "sentence-transformers/all-MiniLM-L6-v2": 384,
}


def get_embedding_model(explicit_model: str | None = None) -> str:
    return explicit_model or os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)


def get_model_token_limit(model: str) -> int:
    return MODEL_TOKEN_LIMITS.get(model, 256)


def get_model_char_limit(model: str) -> int:
    return get_model_token_limit(model) * APPROX_CHARS_PER_TOKEN


def ensure_embeddings_dir(osii_root: Path) -> Path:
    path = osii_embeddings_dir(osii_root).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_dir(osii_root: Path) -> Path:
    path = ensure_embeddings_dir(osii_root) / "build"
    path.mkdir(parents=True, exist_ok=True)
    return path


def embeddings_index_path(osii_root: Path) -> Path:
    return ensure_embeddings_dir(osii_root) / "segments.faiss"


def embeddings_mapping_path(osii_root: Path) -> Path:
    return ensure_embeddings_dir(osii_root) / "segments.mapping.jsonl"


def embeddings_meta_path(osii_root: Path) -> Path:
    return ensure_embeddings_dir(osii_root) / "segments.meta.toml"


def build_index_tmp_path(osii_root: Path) -> Path:
    return build_dir(osii_root) / "segments.faiss.tmp"


def build_mapping_tmp_path(osii_root: Path) -> Path:
    return build_dir(osii_root) / "segments.mapping.partial.jsonl"


def truncate_for_embedding(text: str, *, max_chars: int) -> tuple[str, str | None]:
    if len(text) <= max_chars:
        return text, None

    truncated = text[:max_chars].rstrip()
    warning = (
        f"Text chunk exceeded approximate embedding limit "
        f"({len(text)} chars > {max_chars} chars); truncated before embedding."
    )
    return truncated, warning


def collect_text_chunks(
    osii_root: Path,
    *,
    model: str,
    chunking_method: str,
    chunk_size: int,
    chunk_overlap: int,
) -> tuple[list[dict], list[str]]:
    _, rows = write_chunk_manifest(
        osii_root,
        method=chunking_method,
        chunk_size=chunk_size,
        overlap=chunk_overlap,
    )

    items = []
    warnings = []
    max_chars = get_model_char_limit(model)

    for row in rows:
        text = row.get("text") or ""
        if not text:
            continue

        truncated_text, warning = truncate_for_embedding(text, max_chars=max_chars)
        if warning:
            warnings.append(f"{row.get('source_relpath')} :: {row.get('chunk_id')} :: {warning}")

        items.append(
            {
                "chunk_id": row["chunk_id"],
                "file_id": row["file_id"],
                "source_relpath": row["source_relpath"],
                "chunk_method": row["chunk_method"],
                "chunk_index": row["chunk_index"],
                "char_start": row["char_start"],
                "char_end": row["char_end"],
                "source_text_representation": row["source_text_representation"],
                "source_text_kind": row["source_text_kind"],
                "text": truncated_text,
                "truncated": warning is not None,
            }
        )

    return items, warnings


def is_context_length_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return (
        "maximum context length" in msg
        or "contextwindowexceedederror" in msg
        or ("requested" in msg and "tokens" in msg and "embedding" in msg)
    )


def more_aggressive_truncation(text: str) -> list[str]:
    current = len(text)
    candidates = []

    for cap in (1024, 768, 512):
        if current > cap:
            candidates.append(text[:cap].rstrip())

    seen = set()
    out = []
    for t in candidates:
        if t and t not in seen:
            out.append(t)
            seen.add(t)
    return out


def _embed_batch(client: Any, model: str, batch: list[str], retries: int = 3):
    last_exc = None
    for attempt in range(retries):
        try:
            response = client.embeddings.create(
                model=model,
                input=batch,
            )
            return [row.embedding for row in response.data]
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(1.0 * (attempt + 1))
    raise last_exc


def load_partial_mapping(osii_root: Path) -> list[dict]:
    path = build_mapping_tmp_path(osii_root)
    if not path.exists():
        return []

    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def append_partial_mapping_row(osii_root: Path, row: dict) -> None:
    path = build_mapping_tmp_path(osii_root)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def save_checkpoint_index(osii_root: Path, index) -> Path:
    path = build_index_tmp_path(osii_root)
    faiss.write_index(index, str(path))
    return path


def finalize_outputs(
    osii_root: Path,
    *,
    model: str,
    index,
    final_mapping_rows: list[dict],
    warnings: list[str],
    skipped: list[str],
    chunking_method: str,
    chunk_size: int,
    chunk_overlap: int,
) -> tuple[Path, Path, Path]:
    final_index = embeddings_index_path(osii_root)
    final_mapping = embeddings_mapping_path(osii_root)
    final_meta = embeddings_meta_path(osii_root)

    faiss.write_index(index, str(final_index))

    with final_mapping.open("w", encoding="utf-8") as f:
        for row in final_mapping_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    payload = {
        "embeddings": {
            "model": model,
            "count": len(final_mapping_rows),
            "dimension": index.d,
            "normalized": True,
            "index_type": "faiss.IndexFlatIP",
            "unit": "derived-text-chunk",
            "max_tokens": get_model_token_limit(model),
            "approx_chars_per_token": APPROX_CHARS_PER_TOKEN,
            "max_chars": get_model_char_limit(model),
        },
        "chunking": {
            "method": chunking_method,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "chunks_manifest": str(embeddings_chunks_manifest_path(osii_root)),
        },
        "lexical": {
            "index_type": "bm25s",
            "chunk_manifest_path": str(embeddings_chunks_manifest_path(osii_root)),
        },
        "stats": {
            "truncated_count": sum(1 for row in final_mapping_rows if row.get("truncated")),
            "skipped_count": len(skipped),
        },
        "warnings": warnings,
        "skipped": skipped,
    }
    final_meta.write_text(tomli_w.dumps(payload), encoding="utf-8")

    shutil.rmtree(build_dir(osii_root), ignore_errors=True)

    return final_index, final_mapping, final_meta


def embed_collection_resumable(
    osii_root: Path,
    *,
    model: str,
    batch_size: int = 1,
    checkpoint_every: int = 100,
    chunking_method: str = "paragraph",
    chunk_size: int = 1200,
    chunk_overlap: int = 200,
) -> tuple[Path, Path, Path]:
    client = create_shirty_client()

    items, warnings = collect_text_chunks(
        osii_root,
        model=model,
        chunking_method=chunking_method,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    partial_rows = load_partial_mapping(osii_root)
    already_done = len(partial_rows)

    skipped: list[str] = []
    final_rows = list(partial_rows)

    print(f"Collected {len(items)} candidate text chunks.")
    if already_done:
        print(f"Resuming from checkpoint: {already_done} chunk(s) already embedded.")

    if warnings:
        print(f"WARNING: {len(warnings)} chunk(s) were truncated before embedding.")
        for w in warnings[:20]:
            print(f"  - {w}")
        if len(warnings) > 20:
            print(f"  ... and {len(warnings) - 20} more")

    if already_done >= len(items):
        if not build_index_tmp_path(osii_root).exists():
            raise RuntimeError("Partial mapping exists but FAISS checkpoint is missing.")
        index = faiss.read_index(str(build_index_tmp_path(osii_root)))
        build_bm25_index(osii_root)
        return finalize_outputs(
            osii_root,
            model=model,
            index=index,
            final_mapping_rows=final_rows,
            warnings=warnings,
            skipped=skipped,
            chunking_method=chunking_method,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    index = None
    if build_index_tmp_path(osii_root).exists():
        index = faiss.read_index(str(build_index_tmp_path(osii_root)))

    success_since_checkpoint = 0

    for item_idx in range(already_done, len(items)):
        item = items[item_idx]
        text = item["text"]

        try_texts = [text] + more_aggressive_truncation(text)
        embedded = False
        last_exc = None

        for candidate_text in try_texts:
            try:
                vectors = _embed_batch(client, model, [candidate_text], retries=3)
                vec = np.array(vectors, dtype="float32")
                faiss.normalize_L2(vec)

                if index is None:
                    index = faiss.IndexFlatIP(vec.shape[1])

                index.add(vec)

                faiss_id = len(final_rows)
                row = {
                    "faiss_id": faiss_id,
                    "chunk_id": item["chunk_id"],
                    "file_id": item["file_id"],
                    "source_relpath": item["source_relpath"],
                    "chunk_method": item["chunk_method"],
                    "chunk_index": item["chunk_index"],
                    "char_start": item["char_start"],
                    "char_end": item["char_end"],
                    "source_text_representation": item["source_text_representation"],
                    "source_text_kind": item["source_text_kind"],
                    "truncated": item["truncated"] or (candidate_text != text),
                }
                append_partial_mapping_row(osii_root, row)
                final_rows.append(row)

                embedded = True
                success_since_checkpoint += 1
                break

            except Exception as exc:
                last_exc = exc
                if not is_context_length_error(exc):
                    break

        if not embedded:
            skipped.append(
                f"{item['source_relpath']} :: {item['chunk_id']} :: {last_exc}"
            )
            print(f"WARNING: skipped chunk after embedding failures: {item['source_relpath']} :: {item['chunk_id']}")
            continue

        if index is not None and success_since_checkpoint >= checkpoint_every:
            save_checkpoint_index(osii_root, index)
            success_since_checkpoint = 0

    if index is None:
        raise RuntimeError("No vectors were successfully embedded.")

    save_checkpoint_index(osii_root, index)
    build_bm25_index(osii_root)

    return finalize_outputs(
        osii_root,
        model=model,
        index=index,
        final_mapping_rows=final_rows,
        warnings=warnings,
        skipped=skipped,
        chunking_method=chunking_method,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
