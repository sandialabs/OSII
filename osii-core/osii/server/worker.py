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
from collections.abc import Callable
import urllib.error

from sqlalchemy.exc import OperationalError, SQLAlchemyError

from osii.indexing.chunking import _structured_window_spans
from osii.persistence.postgres import PostgresStore, identifier
from osii.processor_sdk.client import ProcessorClient, ProcessorClientError
from osii.processor_sdk.models import DocumentInput, ExtractionRequest, ExtractionResponse
from osii.server.config import Settings
from osii.server.sources import resolve_directory
from osii.model_provider import ModelProvider, ProviderError


class IngestionError(ValueError):
    pass


def _normalize_extraction(response: ExtractionResponse) -> tuple[ExtractionResponse, int]:
    # PostgreSQL text and JSONB cannot represent NUL. Replace one code point
    # with one code point before creating spans; originals remain untouched.
    replacements = 0

    def normalize(value):
        nonlocal replacements
        if isinstance(value, str):
            replacements += value.count("\x00")
            return value.replace("\x00", "\ufffd")
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()}
        return value

    payload = normalize(response.model_dump(mode="json"))
    return ExtractionResponse.model_validate(payload), replacements


def ingest_file(store: PostgresStore, provider: ModelProvider, extractor: ProcessorClient,
                root: Path, path: Path, *, max_bytes: int = 50 * 1024 * 1024,
                ocr: ProcessorClient | None = None, force: bool = False) -> str:
    target = path.resolve()
    if not target.is_relative_to(root.resolve()) or path.is_symlink():
        raise IngestionError("Source escapes the configured dataset or is a symbolic link")
    if target.stat().st_size > max_bytes:
        raise IngestionError("Source exceeds the 50 MiB processing limit")
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
    response, nul_replacements = _normalize_extraction(response)
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
    if nul_replacements:
        doc["metadata"]["normalization"] = {"nul_replacements": nul_replacements, "replacement": "U+FFFD"}
    artifact_rows = [{"id": identifier(), "file_id": fid, "kind": artifact.kind,
        "payload": artifact.model_dump(mode="json")} for artifact in response.artifacts]
    store.commit_document(doc, rows, response.model_dump(mode="json"), artifact_rows)
    return "processed"


def failure_reason(exc: Exception) -> str:
    """Operator diagnostics without provider bodies, SQL parameters, or text."""
    if isinstance(exc, (IngestionError, ProviderError)):
        return str(exc)
    if isinstance(exc, ProcessorClientError):
        cause = exc.__cause__
        if isinstance(cause, urllib.error.HTTPError):
            return f"Extractor request failed (HTTP {cause.code})"
        return "Extractor unavailable or returned an invalid response"
    if isinstance(exc, TimeoutError):
        return "Extractor request timed out"
    if isinstance(exc, OSError):
        return f"Source could not be read ({type(exc).__name__})"
    if isinstance(exc, SQLAlchemyError):
        return f"PostgreSQL persistence failed ({type(exc).__name__})"
    return f"Document processing failed ({type(exc).__name__})"


def ingest_batch(store: PostgresStore, provider: ModelProvider, extractor: ProcessorClient,
                 root: Path, *, report: Callable[[str], None], stopping: threading.Event,
                 ocr: ProcessorClient | None = None, force: bool = False, source_directory: str = ".") -> bool:
    if not root.is_dir():
        raise IngestionError("Configured source directory is unavailable; reconnect it and retry.")
    counts = {"processed": 0, "unchanged": 0, "failed": 0}
    scan_root = resolve_directory(root, source_directory)
    for path in sorted(scan_root.rglob("*")):
        if stopping.is_set():
            raise IngestionError("Worker shutdown interrupted ingestion; committed documents are retained. Retry to resume.")
        relative = path.relative_to(root).as_posix()
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        try:
            if path.is_dir():
                continue
            report(f"processing: {relative}")
            status = ingest_file(store, provider, extractor, root, path, ocr=ocr, force=force)
        except OperationalError:
            # Database connectivity is a batch failure, not a broken PDF.
            raise
        except Exception as exc:
            counts["failed"] += 1
            report(f"failed: {relative}: {failure_reason(exc)}")
        else:
            counts[status] += 1
            report(f"{status}: {relative}")
    report("Batch completed: " + ", ".join(f"{name}={count}" for name, count in counts.items()))
    # An error status means all files were visited but some need attention.
    return counts["failed"] > 0


def run(settings: Settings | None = None) -> None:
    settings = settings or Settings.environment()
    store = PostgresStore(settings.database_url)
    store.ready()
    provider = settings.provider()
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
        logs, failed = list(job["logs"]), False

        def report(entry: str) -> None:
            if not store.progress(job["id"], worker, entry):
                raise IngestionError("Worker no longer owns this job; processing stopped.")
            logs.append(entry)

        try:
            # One writer for the shared corpus, including when an operator starts
            # another worker accidentally. Source originals are never modified.
            with store.engine.connect() as lock:
                lock.execute(__import__("sqlalchemy").text("SELECT pg_advisory_lock(914035)"))
                try:
                    failed = ingest_batch(store, provider, extractor, settings.source_root,
                        report=report, stopping=stopping, ocr=ocr, force=bool(job["payload"].get("force")),
                        source_directory=job["payload"].get("source_directory", "."))
                finally:
                    lock.execute(__import__("sqlalchemy").text("SELECT pg_advisory_unlock(914035)"))
        except Exception as exc:
            logs.append("Batch stopped: " + failure_reason(exc))
            failed = True
        finally:
            finished.set()
            thread.join(timeout=2)
            store.finish(job["id"], worker, logs, failed)


if __name__ == "__main__":
    run()
