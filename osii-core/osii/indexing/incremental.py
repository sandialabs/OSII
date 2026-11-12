"""Selected-document embeddings with durable chunk checkpoints and atomic publication."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import tomllib

import faiss
import numpy as np
import tomli_w

from osii.domain.artifacts.artifact_staleness import clear_artifacts_stale
from osii.domain.catalog_db import refresh_semantic_indexes
from osii.domain.model_provider_config import selected_processor
from osii.domain.storage.embedding_snapshot import (
    active_snapshot,
    embedding_writer,
    new_snapshot,
    publish_snapshot,
)
from osii.domain.storage.store import embeddings_chunks_manifest_path
from osii.indexing.chunking import (
    generate_chunk_records,
    DEFAULT_CHUNKING_METHOD,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_CHUNK_OVERLAP,
)
from osii.indexing.common import (
    IncompatibleIndexError,
    _embed_batch,
    _embedding_mapping_row,
    embedding_input_key,
    ensure_embeddings_dir,
    get_embedding_model,
    get_model_char_limit,
    is_context_length_error,
    more_aggressive_truncation,
    truncate_for_embedding,
)
from osii.model_clients import create_embedding_client
from osii.search.lexical import build_bm25_index


class IncrementalEmbeddingError(RuntimeError):
    def __init__(self, report: dict):
        self.report = report
        super().__init__(
            f"Embeddings failed for {len(report['failures'])} document(s); successful chunks are checkpointed. Retry this run to continue."
        )


def _existing(directory: Path, model: str, provider: str):
    snapshot = active_snapshot(directory)
    names = [
        snapshot / name
        for name in ("segments.faiss", "segments.mapping.jsonl", "segments.meta.toml")
    ]
    if not any(path.exists() for path in names):
        if (directory / "current.json").exists():
            raise IncompatibleIndexError(
                "The published snapshot is missing; restore it before adding embeddings"
            )
        return None, [], {}
    if not all(path.exists() for path in names):
        raise IncompatibleIndexError(
            "The existing index is incomplete; restore its snapshot or explicitly rebuild it"
        )
    metadata = tomllib.loads(names[2].read_text(encoding="utf-8"))
    meta = metadata["embeddings"]
    # Old direct HTTP clients wrote the generic provider label in this same
    # provider/model namespace. Preserve those vectors during the first upgrade.
    if meta["model"] != model or meta.get("provider_id", meta.get("provider")) not in {
        provider,
        "openai-compatible",
    }:
        raise IncompatibleIndexError(
            "Existing vectors belong to another provider/model; select its connection or build a separate index"
        )
    index = faiss.read_index(str(names[0]))
    rows = [
        json.loads(line)
        for line in names[1].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if (
        not isinstance(index, faiss.IndexFlatIP)
        or index.ntotal != len(rows)
        or index.d != meta["dimension"]
        or len(rows) != meta["count"]
        or any(row.get("faiss_id") != i for i, row in enumerate(rows))
    ):
        raise IncompatibleIndexError(
            "The existing index and mapping disagree; restore or explicitly rebuild them"
        )
    return index, rows, metadata


def _vectors(
    client, model: str, texts: list[str], dimension: int | None, digest: str | None
):
    values = np.asarray(_embed_batch(client, model, texts), dtype="float32")
    if (
        values.ndim != 2
        or values.shape[0] != len(texts)
        or not 1 <= values.shape[1] <= 65536
    ):
        raise ValueError("Embedding service returned an invalid vector shape")
    if not np.isfinite(values).all() or np.any(np.linalg.norm(values, axis=1) <= 1e-12):
        raise ValueError("Embedding service returned a nonfinite or zero vector")
    if dimension is not None and values.shape[1] != dimension:
        raise IncompatibleIndexError(
            "Embedding dimensions changed; existing vectors and checkpoints were preserved"
        )
    if getattr(client, "model_name", model) != model:
        raise IncompatibleIndexError(
            "Embedding service returned a different model identity"
        )
    current_digest = getattr(client, "model_digest", None)
    if digest and current_digest and digest != current_digest:
        raise IncompatibleIndexError(
            "Embedding model digest changed; existing vectors and checkpoints were preserved"
        )
    faiss.normalize_L2(values)
    return values


def _merge_chunks(
    osii_root: Path,
    completed: set[str],
    documents: dict[str, list[dict]],
    *,
    replace_all: bool = False,
) -> None:
    path = embeddings_chunks_manifest_path(osii_root)
    fd, name = tempfile.mkstemp(prefix=".chunks-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            if path.exists() and not replace_all:
                with path.open(encoding="utf-8") as previous:
                    for line in previous:
                        if (
                            line.strip()
                            and json.loads(line).get("file_id") not in completed
                        ):
                            output.write(line.rstrip("\n") + "\n")
            for file_id in sorted(completed):
                for row in documents[file_id]:
                    output.write(json.dumps(row, ensure_ascii=False) + "\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)
    build_bm25_index(osii_root)


def embed_selected_documents(
    osii_root: Path,
    file_ids: list[str],
    *,
    model: str | None = None,
    batch_size: int = 64,
    chunking_method: str = DEFAULT_CHUNKING_METHOD,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    expected_identity: dict | None = None,
    on_progress: Callable[[dict], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    rebuild_id: str | None = None,
) -> dict:
    """Only selected sidecar text reaches the provider. Originals are never opened.

    Responses are committed before progress is reported. A response lost before
    its commit may be requested again; this is not exactly-once provider billing.
    """
    with embedding_writer(osii_root):
        return _embed_selected(
            osii_root,
            sorted(set(file_ids)),
            model=model,
            batch_size=batch_size,
            chunking_method=chunking_method,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            expected_identity=expected_identity,
            on_progress=on_progress,
            should_stop=should_stop,
            rebuild_id=rebuild_id,
        )


def _embed_selected(
    osii_root,
    file_ids,
    *,
    model,
    batch_size,
    chunking_method,
    chunk_size,
    chunk_overlap,
    expected_identity,
    on_progress,
    should_stop,
    rebuild_id,
):
    model = model or get_embedding_model()
    provider = selected_processor("embedder", osii_root=osii_root)
    client = create_embedding_client()
    identity = {
        "provider": provider,
        "model": model,
        "endpoint_hash": hashlib.sha256(
            str(getattr(client, "base_url", "")).encode()
        ).hexdigest(),
        "processor_version": str(getattr(client, "descriptor", {}).get("version", "")),
    }
    if expected_identity is not None and identity != expected_identity:
        raise IncompatibleIndexError(
            "This run's embedding connection changed; restore its provider/model/endpoint before retrying"
        )
    directory = ensure_embeddings_dir(osii_root, model=model, provider=provider)
    if rebuild_id is not None:
        import re

        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", rebuild_id):
            raise ValueError("Invalid full rebuild identity")
        old_index, old_rows, metadata = None, [], {}
    else:
        old_index, old_rows, metadata = _existing(directory, model, provider)
    old_meta = metadata.get("embeddings", {})
    report = {
        "identity": identity,
        "total_documents": len(file_ids),
        "completed_documents": 0,
        "embedded_chunks": 0,
        "reused_chunks": 0,
        "failures": {},
        "paused": False,
    }
    documents, keys = {}, {}
    for file_id in file_ids:
        try:
            rows = generate_chunk_records(
                osii_root,
                file_ids={file_id},
                method=chunking_method,
                chunk_size=chunk_size,
                overlap=chunk_overlap,
            )
            if not rows:
                raise ValueError("Document has no extracted text to embed")
            documents[file_id] = rows
            keys[file_id] = [embedding_input_key(row, model) for row in rows]
        except (OSError, ValueError, RuntimeError) as exc:
            report["failures"][file_id] = str(exc)
    # WAL and FULL commits retain each successful response across worker exits.
    with closing(
        sqlite3.connect(
            directory
            / (
                f"full-build-{rebuild_id}.sqlite3"
                if rebuild_id
                else "incremental.sqlite3"
            ),
            timeout=30,
        )
    ) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.executescript("""CREATE TABLE IF NOT EXISTS binding(id INTEGER PRIMARY KEY CHECK(id=1), identity TEXT NOT NULL, dimension INTEGER, digest TEXT);
            CREATE TABLE IF NOT EXISTS vectors(key TEXT PRIMARY KEY,row_json TEXT NOT NULL,vector BLOB NOT NULL);""")
        binding = conn.execute(
            "SELECT identity,dimension,digest FROM binding WHERE id=1"
        ).fetchone()
        if binding and json.loads(binding[0]) != identity:
            raise IncompatibleIndexError(
                "The cached embedding connection changed; restore it or use a separate provider/model index"
            )
        dimension = binding[1] if binding else old_meta.get("dimension")
        digest = binding[2] if binding else old_meta.get("model_digest")
        if digest and getattr(client, "model_digest", None) not in {None, digest}:
            raise IncompatibleIndexError(
                "Embedding model digest changed; restore the original model before retrying"
            )
        if old_index is not None and dimension != old_index.d:
            raise IncompatibleIndexError(
                "Checkpoint dimensions disagree with the published index"
            )
        conn.execute(
            "INSERT OR IGNORE INTO binding VALUES(1,?,?,?)",
            (json.dumps(identity, sort_keys=True), dimension, digest),
        )
        conn.commit()
        cached = {}
        for file_id, desired in keys.items():
            for key in desired:
                row = conn.execute(
                    "SELECT row_json,vector FROM vectors WHERE key=?", (key,)
                ).fetchone()
                if row:
                    mapped = json.loads(row[0])
                    vector = np.frombuffer(row[1], dtype="float32").copy()
                    if (
                        mapped.get("embedding_key") != key
                        or vector.shape != (dimension,)
                        or not np.isfinite(vector).all()
                        or np.linalg.norm(vector) <= 1e-12
                    ):
                        raise IncompatibleIndexError(
                            "An embedding checkpoint is inconsistent; restore it before retrying"
                        )
                    cached[key] = (mapped, vector)
        # New full rebuilds record fingerprints too. Import matches without
        # asking the provider again; fingerprint-less legacy rows stay intact.
        wanted = {key for group in keys.values() for key in group}
        for ordinal, row in enumerate(old_rows):
            key = row.get("embedding_key")
            if key in wanted and key not in cached:
                vector = old_index.reconstruct(ordinal)
                cached[key] = (row, vector)
                conn.execute(
                    "INSERT OR IGNORE INTO vectors VALUES(?,?,?)",
                    (key, json.dumps(row), vector.astype("float32").tobytes()),
                )
        conn.commit()
        report["reused_chunks"] = len(cached)

        def progress():
            finished = [
                file_id
                for file_id, group in keys.items()
                if all(key in cached for key in group)
            ]
            report["completed_documents"] = len(finished)
            if rebuild_id:
                report["completed_file_ids"] = finished
            if on_progress:
                on_progress(report.copy())

        def commit(items, vectors, inputs):
            nonlocal dimension, digest
            dimension = vectors.shape[1]
            digest = getattr(client, "model_digest", None) or digest
            with conn:
                conn.execute(
                    "UPDATE binding SET dimension=?,digest=? WHERE id=1",
                    (dimension, digest),
                )
                for (row, key), vector, text in zip(items, vectors, inputs):
                    item = {**row, "embedding_key": key}
                    mapped = _embedding_mapping_row(
                        item,
                        faiss_id=0,
                        source_item_index=0,
                        truncated=text != row["text"],
                    )
                    mapped.update(
                        embedding_key=key,
                        embedded_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                        chunk_size=chunk_size,
                        chunk_overlap=row.get("chunk_overlap", chunk_overlap),
                    )
                    conn.execute(
                        "INSERT OR REPLACE INTO vectors VALUES(?,?,?)",
                        (key, json.dumps(mapped), vector.tobytes()),
                    )
                    cached[key] = (mapped, vector)
            report["embedded_chunks"] += len(items)
            progress()

        progress()  # Pin the connection in the durable run before any model call.
        pending = [
            (row, key)
            for file_id, rows in documents.items()
            for row, key in zip(rows, keys[file_id])
            if key not in cached
        ]
        for start in range(0, len(pending), max(1, batch_size)):
            if should_stop and should_stop():
                report["paused"] = True
                break
            items = pending[start : start + max(1, batch_size)]
            inputs = [
                truncate_for_embedding(
                    row["text"], max_chars=get_model_char_limit(model)
                )[0]
                for row, _ in items
            ]
            try:
                values = _vectors(client, model, inputs, dimension, digest)
            except IncompatibleIndexError:
                raise
            except Exception:
                # Isolate a bad chunk/provider response, keeping healthy siblings.
                for item, text in zip(items, inputs):
                    if should_stop and should_stop():
                        report["paused"] = True
                        break
                    candidates = [text]
                    last_error = None
                    while candidates:
                        candidate = candidates.pop(0)
                        try:
                            values = _vectors(
                                client, model, [candidate], dimension, digest
                            )
                        except IncompatibleIndexError:
                            raise
                        except Exception as exc:
                            last_error = exc
                            if candidate == text and is_context_length_error(exc):
                                candidates.extend(more_aggressive_truncation(text))
                        else:
                            commit([item], values, [candidate])
                            break
                    else:
                        report["failures"][item[0]["file_id"]] = str(last_error)
                if report["paused"]:
                    break
            else:
                commit(items, values, inputs)
        completed = {
            file_id
            for file_id, group in keys.items()
            if all(key in cached for key in group)
        }
        # An edited/replaced extraction during an HTTP request must not publish
        # vectors as current for a different text revision.
        for file_id in list(completed):
            try:
                fresh = generate_chunk_records(
                    osii_root,
                    file_ids={file_id},
                    method=chunking_method,
                    chunk_size=chunk_size,
                    overlap=chunk_overlap,
                )
            except (OSError, ValueError, RuntimeError):
                fresh = []
            if [embedding_input_key(row, model) for row in fresh] != keys[file_id]:
                completed.remove(file_id)
                report["failures"][file_id] = (
                    "Text changed while embedding; retry the current text revision"
                )
        publish = bool(completed) and (
            not rebuild_id
            or (
                not report["failures"]
                and not report["paused"]
                and len(completed) == len(file_ids)
            )
        )
        if publish:
            index = faiss.IndexFlatIP(dimension)
            final_rows = []
            for ordinal, row in enumerate(old_rows):
                if row["file_id"] not in completed:
                    index.add(old_index.reconstruct(ordinal).reshape(1, -1))
                    final_rows.append({**row, "faiss_id": len(final_rows)})
            for file_id in sorted(completed):
                for current_row, key in zip(documents[file_id], keys[file_id]):
                    row, vector = cached[key]
                    mapped = _embedding_mapping_row(
                        current_row,
                        faiss_id=len(final_rows),
                        source_item_index=0,
                        truncated=row.get("truncated", False),
                    )
                    mapped.update(
                        embedding_key=key,
                        embedded_text_sha256=row.get("embedded_text_sha256", ""),
                    )
                    index.add(vector.reshape(1, -1))
                    final_rows.append(mapped)
            snapshot = new_snapshot(directory)
            faiss.write_index(index, str(snapshot / "segments.faiss"))
            (snapshot / "segments.mapping.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in final_rows), encoding="utf-8"
            )
            meta = {
                **metadata,
                "embeddings": {
                    **old_meta,
                    "model": model,
                    "provider": provider,
                    "provider_id": provider,
                    "count": len(final_rows),
                    "dimension": dimension,
                    "normalized": True,
                    "semantic": getattr(client, "semantic", None)
                    if getattr(client, "semantic", None) is not None
                    else provider != "local.hashing",
                    "created_utc": datetime.now(UTC).isoformat(),
                    **({"rebuild_run_id": rebuild_id} if rebuild_id else {}),
                    **({"model_digest": digest} if digest else {}),
                },
                "chunking": {
                    "method": chunking_method,
                    "chunk_size": chunk_size,
                    "chunk_overlap": chunk_overlap,
                    "per_document": True,
                },
            }
            if rebuild_id:
                from osii.indexing.common import (
                    get_model_token_limit,
                    APPROX_CHARS_PER_TOKEN,
                )

                meta["embeddings"].update(
                    index_type="faiss.IndexFlatIP",
                    unit="derived-text-chunk",
                    max_tokens=get_model_token_limit(model),
                    approx_chars_per_token=APPROX_CHARS_PER_TOKEN,
                    max_chars=get_model_char_limit(model),
                )
                meta["lexical"] = {
                    "index_type": "bm25s",
                    "chunk_manifest_path": str(
                        embeddings_chunks_manifest_path(osii_root)
                    ),
                }
                meta["stats"] = {
                    "truncated_count": sum(
                        bool(row.get("truncated")) for row in final_rows
                    ),
                    "skipped_count": 0,
                }
                meta["warnings"], meta["skipped"] = [], []
            (snapshot / "segments.meta.toml").write_text(
                tomli_w.dumps(meta), encoding="utf-8"
            )
            publish_snapshot(directory, snapshot)
            for file_id in completed:
                clear_artifacts_stale(osii_root, file_id, "embeddings", "search_chunks")
            _merge_chunks(osii_root, completed, documents, replace_all=bool(rebuild_id))
            if rebuild_id:
                # New vector dimensions/configuration may supersede an older
                # incremental cache; the next intake can import this snapshot.
                for suffix in ("", "-wal", "-shm"):
                    (directory / ("incremental.sqlite3" + suffix)).unlink(
                        missing_ok=True
                    )
            refresh_semantic_indexes(osii_root)
        report["completed_documents"] = len(completed)
        if rebuild_id:
            report["completed_file_ids"] = sorted(completed)
        if on_progress:
            on_progress(report.copy())
        if report["failures"] and not report["paused"]:
            raise IncrementalEmbeddingError(report)
        return report
