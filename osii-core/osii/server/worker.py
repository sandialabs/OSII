"""Sequential bounded processing with transactional PostgreSQL commits."""
from __future__ import annotations

import base64
import hashlib
import mimetypes
import os
from pathlib import Path
import signal
import threading
import time

from osii.indexing.chunking import _structured_window_spans
from osii.persistence.postgres import PostgresStore, identifier
from osii.processor_sdk.client import ProcessorClient
from osii.processor_sdk.models import DocumentInput, ExtractionRequest
from osii.server.config import Settings
from osii.model_provider import ModelProvider


class IngestionError(ValueError):
    pass


def ingest_file(store: PostgresStore, provider: ModelProvider, extractor: ProcessorClient,
                root: Path, path: Path, *, max_bytes: int = 50 * 1024 * 1024,
                ocr: ProcessorClient | None = None, force: bool = False) -> str:
    target = path.resolve()
    if not target.is_relative_to(root.resolve()) or path.is_symlink():
        raise ValueError("Source escapes the configured dataset")
    if target.stat().st_size > max_bytes:
        raise ValueError("Source exceeds the 50 MiB processing limit")
    original = target.read_bytes()
    relative = target.relative_to(root.resolve()).as_posix()
    sha = hashlib.sha256(original).hexdigest()
    fid = "sha256-" + sha
    configuration = store.configuration()
    previous = store.document(fid)
    if not force and previous and previous["active"] and previous["source_relpath"] == relative and previous["sha256"] == sha and previous["metadata"].get("embedding_model", "") == configuration.get("embedding_model", ""):
        return "unchanged"
    media = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    response = extractor.extract(ExtractionRequest(request_id=identifier(), document=DocumentInput(
        file_id=fid, filename=path.name, media_type=media, content_base64=base64.b64encode(original).decode())))
    if not any(segment.text.strip() for segment in response.segments) and ocr:
        response = ocr.extract(ExtractionRequest(request_id=identifier(), document=DocumentInput(
            file_id=fid, filename=path.name, media_type=media, content_base64=base64.b64encode(original).decode())))
    if not any(segment.text.strip() for segment in response.segments):
        raise IngestionError("No usable text extracted. Configure OSII_OCR_URL for scanned documents, then retry.")
    pieces, spans, position = [], [], 0
    for segment in response.segments:
        if pieces:
            pieces.append("\n")
            position += 1
        start = position
        pieces.append(segment.text)
        position += len(segment.text)
        spans.append({"id": segment.id, "char_start": start, "char_end": position,
            "source_origin": segment.source_origin})
    content = "".join(pieces)
    rows = []
    for i, (start, end) in enumerate(_structured_window_spans(content, 768, 128)):
        origins = [s for s in spans if s["char_start"] < end and s["char_end"] > start]
        rows.append({"chunk_id": f"{fid}:{i}", "file_id": fid, "text": content[start:end],
            "char_start": start, "char_end": end, "source_origin": {"segments": origins},
            "embedding": None, "embedding_model": None})
    model = configuration.get("embedding_model", "")
    if model:
        for start in range(0, len(rows), 32):
            batch = rows[start:start + 32]
            vectors = provider.embed(model, [row["text"] for row in batch])
            for row, vector in zip(batch, vectors):
                row.update(embedding=vector, embedding_model=model)
    doc = {"file_id": fid, "source_relpath": relative, "sha256": sha, "filename": path.name,
        "media_type": media, "size_bytes": len(original), "text": content,
        "metadata": {"segments": spans, "extractor": response.processor.model_dump(mode="json"), "embedding_model": model}}
    artifact_rows = [{"id": identifier(), "file_id": fid, "kind": artifact.kind,
        "payload": artifact.model_dump(mode="json")} for artifact in response.artifacts]
    store.commit_document(doc, rows, response.model_dump(mode="json"), artifact_rows)
    return "processed"


def run(settings: Settings | None = None) -> None:
    settings = settings or Settings.environment()
    store = PostgresStore(settings.database_url)
    store.ready()
    provider = ModelProvider(settings.model_url, settings.model_key)
    extractor = ProcessorClient(settings.extractor_url, timeout=120)
    ocr = ProcessorClient(settings.ocr_url, timeout=180) if settings.ocr_url else None
    worker, stopping = identifier(), threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stopping.set())
    while not stopping.is_set():
        job = store.claim(worker)
        if not job:
            stopping.wait(1)
            continue
        finished = threading.Event()

        def heartbeat():
            while not finished.wait(10):
                store.heartbeat(job["id"], worker)

        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        logs, failed = [], False
        try:
            # One writer for the shared corpus, including when an operator starts
            # another worker accidentally. Source originals are never modified.
            with store.engine.connect() as lock:
                lock.execute(__import__("sqlalchemy").text("SELECT pg_advisory_lock(914035)"))
                try:
                    for path in sorted(settings.source_root.rglob("*")):
                        if stopping.is_set():
                            raise RuntimeError("Worker shutdown interrupted ingestion")
                        if not path.is_file() or any(p.startswith(".") for p in path.relative_to(settings.source_root).parts):
                            continue
                        status = ingest_file(store, provider, extractor, settings.source_root, path, ocr=ocr, force=bool(job["payload"].get("force")))
                        logs.append(f"{status}: {path.relative_to(settings.source_root).as_posix()}")
                finally:
                    lock.execute(__import__("sqlalchemy").text("SELECT pg_advisory_unlock(914035)"))
        except IngestionError as exc:
            logs.append(str(exc))
            failed = True
        except Exception:
            # No raw provider response, secret, source text, or traceback is stored.
            logs.append("Processing failed. Check extractor/model availability and source format; retry ingestion after correcting the cause.")
            failed = True
        finally:
            finished.set()
            thread.join(timeout=2)
            store.finish(job["id"], worker, logs, failed)


if __name__ == "__main__":
    run()
