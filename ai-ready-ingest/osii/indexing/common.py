from pathlib import Path
from datetime import UTC, datetime
import hashlib
import json
import os
import re
import shutil
import time

import faiss
import numpy as np
import tomli_w

from typing import Any

from osii.model_clients import create_embedding_client

from osii.domain.storage.store import (
    embeddings_chunks_manifest_path,
    embeddings_dir as osii_embeddings_dir,
)
from osii.indexing.chunking import write_chunk_manifest
from osii.search.lexical import build_bm25_index
from osii.domain.catalog_db import rebuild_catalog
from osii.domain.model_provider_config import selected_model, selected_processor
from osii.domain.storage.atomic import atomic_write_text


DEFAULT_EMBEDDING_MODEL = "osii-local-hashing-v1"
APPROX_CHARS_PER_TOKEN = 4

MODEL_TOKEN_LIMITS: dict[str, int] = {}


def get_embedding_model(explicit_model: str | None = None) -> str:
    return explicit_model or selected_model("embedder")


def get_model_token_limit(model: str) -> int:
    return MODEL_TOKEN_LIMITS.get(model, 256)


def get_model_char_limit(model: str) -> int:
    return get_model_token_limit(model) * APPROX_CHARS_PER_TOKEN


def embedding_namespace(model: str | None = None, provider: str | None = None) -> tuple[str, str]:
    provider_name = provider or selected_processor("embedder")
    model_name = model or get_embedding_model()
    safe_provider = re.sub(r"[^A-Za-z0-9_.-]+", "-", provider_name).strip("-") or "unknown"
    safe_model = re.sub(r"[^A-Za-z0-9_.-]+", "-", model_name).strip("-")[:48] or "unknown"
    digest = hashlib.sha256(model_name.encode("utf-8")).hexdigest()[:12]
    return safe_provider, f"{safe_model}-{digest}"


def ensure_embeddings_dir(osii_root: Path) -> Path:
    provider, model = embedding_namespace()
    path = (osii_embeddings_dir(osii_root).resolve() / "providers" / provider / model)
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
            return client.embed(model=model, texts=batch)
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
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            # A process can stop halfway through its final append. The FAISS
            # checkpoint remains the authority for how many rows are durable.
            break
    return rows


def _write_partial_mapping(osii_root: Path, rows: list[dict]) -> None:
    content = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    atomic_write_text(build_mapping_tmp_path(osii_root), content)


def load_resumable_checkpoint(osii_root: Path):
    """Return only mapping rows committed in the matching FAISS checkpoint."""
    rows = load_partial_mapping(osii_root)
    index_path = build_index_tmp_path(osii_root)
    if not index_path.exists():
        if rows:
            _write_partial_mapping(osii_root, [])
        return None, []

    index = faiss.read_index(str(index_path))
    if index.ntotal > len(rows):
        raise RuntimeError(
            "FAISS checkpoint contains more vectors than its partial mapping; "
            "remove this provider/model build directory and rebuild the index."
        )
    if len(rows) != index.ntotal:
        rows = rows[: index.ntotal]
        _write_partial_mapping(osii_root, rows)
    return index, rows


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
    provider: str | None = None,
    model_digest: str | None = None,
    endpoint_type: str | None = None,
    semantic: bool | None = None,
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
            "provider": provider or "openai-compatible",
            "provider_id": provider or "openai-compatible",
            **({"model_digest": model_digest} if model_digest else {}),
            **({"endpoint_type": endpoint_type} if endpoint_type else {}),
            "semantic": bool(semantic) if semantic is not None else (provider != "local.hashing"),
            "count": len(final_mapping_rows),
            "dimension": index.d,
            "normalized": True,
            "index_type": "faiss.IndexFlatIP",
            "unit": "derived-text-chunk",
            "created_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
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
    rebuild_catalog(osii_root)

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
    client = create_embedding_client()

    items, warnings = collect_text_chunks(
        osii_root,
        model=model,
        chunking_method=chunking_method,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    index, partial_rows = load_resumable_checkpoint(osii_root)
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
        if index is None:
            raise RuntimeError("Partial mapping exists but FAISS checkpoint is missing.")
        build_bm25_index(osii_root)
        return finalize_outputs(
            osii_root,
            model=getattr(client, "model_name", None) or model,
            index=index,
            final_mapping_rows=final_rows,
            warnings=warnings,
            skipped=skipped,
            chunking_method=chunking_method,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            provider=getattr(client, "provider", None),
            model_digest=getattr(client, "model_digest", None),
            endpoint_type=getattr(client, "endpoint_type", None),
            semantic=getattr(client, "semantic", None),
        )

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
                elif index.d != vec.shape[1]:
                    raise IncompatibleIndexError(
                        f"Embedding dimensions changed from {index.d} to {vec.shape[1]}; "
                        "the checkpoint cannot be resumed in a different vector space."
                    )

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
                if isinstance(exc, IncompatibleIndexError):
                    raise
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
        model=getattr(client, "model_name", None) or model,
        index=index,
        final_mapping_rows=final_rows,
        warnings=warnings,
        skipped=skipped,
        chunking_method=chunking_method,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        provider=getattr(client, "provider", None),
        model_digest=getattr(client, "model_digest", None),
        endpoint_type=getattr(client, "endpoint_type", None),
        semantic=getattr(client, "semantic", None),
    )


class IncompatibleIndexError(RuntimeError):
    pass
