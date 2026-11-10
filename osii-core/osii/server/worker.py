"""Sequential bounded processing with transactional PostgreSQL commits."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
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
from sqlalchemy import text

from osii.persistence.postgres import PostgresStore, identifier, now
from osii.domain.storage.commits import ProcessingCommit, SourceRecord, JobCheckpoint, InputRevision
from osii.domain.storage.postgres_commits import PostgresProcessingCommitter
from osii.processor_sdk.client import ProcessorClient, ProcessorClientError
from osii.processor_sdk.models import DocumentInput, ExtractionRequest, ExtractionResponse
from osii.server.config import Settings
from osii.server.sources import resolve_directory
from osii.server.processors import ProcessorError, derived_outputs, SelectedExtractor
from osii.model_provider import ModelProvider, ProviderError
from osii.server.model_connections import ModelConnections, ConfiguredModelProvider


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
                ocr: ProcessorClient | None = None, force: bool = False, embed: bool = True,
                job_owner: tuple[str, str] | None = None, save_variant: bool = False) -> str:
    target = path.resolve()
    if not target.is_relative_to(root.resolve()) or path.is_symlink():
        raise IngestionError("Source escapes the configured dataset or is a symbolic link")
    source_stat = target.stat()
    if source_stat.st_size > max_bytes:
        raise IngestionError("Source exceeds the 50 MiB processing limit")
    original = target.read_bytes()
    relative = target.relative_to(root.resolve()).as_posix()
    sha = hashlib.sha256(original).hexdigest()
    fid = "sha256-" + sha
    configuration = store.configuration()
    model = configuration.get("embedding_model", "") if embed and not save_variant else ""
    previous = store.document(fid)
    if not force and previous and previous["active"] and previous["source_relpath"] == relative and previous["sha256"] == sha and (not embed or previous["metadata"].get("embedding_model", "") == model):
        return "unchanged"
    media = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    request = ExtractionRequest(request_id=identifier(), document=DocumentInput(
        file_id=fid, filename=path.name, media_type=media, content_base64=base64.b64encode(original).decode()))
    response = extractor.extract(request)
    if not any(segment.text.strip() for segment in response.segments) and ocr:
        request = ExtractionRequest(request_id=identifier(), document=DocumentInput(
            file_id=fid, filename=path.name, media_type=media, content_base64=base64.b64encode(original).decode()))
        response = ocr.extract(request)
    if not any(segment.text.strip() for segment in response.segments):
        raise IngestionError("No usable text extracted. Check OCR health in Intake, then choose an OCR extractor and re-extract this file.")
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
    embedding_error = ""
    if model:
        try:
            for start in range(0, len(rows), 32):
                batch = rows[start:start + 32]
                vectors = provider.embed(model, [row["text"] for row in batch])
                for row, vector in zip(batch, vectors):
                    row.update(embedding=vector, embedding_model=model)
        except ProviderError as exc:
            embedding_error = str(exc)
            for row in rows:
                row.update(embedding=None, embedding_model=None)
    doc = {"file_id": fid, "source_relpath": relative, "sha256": sha, "filename": path.name,
        "media_type": media, "size_bytes": len(original), "text": content,
        "metadata": {"source_modified_at": datetime.fromtimestamp(source_stat.st_mtime, timezone.utc).isoformat(), "segments": spans, "extractor": response.processor.model_dump(mode="json"), "embedding_model": model}}
    if embedding_error:
        doc["metadata"].update(embedding_model="", embedding_warning=embedding_error)
    if nul_replacements:
        doc["metadata"]["normalization"] = {"nul_replacements": nul_replacements, "replacement": "U+FFFD"}
    operation = f"{job_owner[0]}:{relative}:extraction" if job_owner else request.request_id
    source = SourceRecord(fid, relative, path.name, media, sha, len(original), doc["metadata"])
    PostgresProcessingCommitter(store.engine).commit(ProcessingCommit(operation, fid, request, response,
        response.processor, source=source, chunks=tuple(rows), make_primary=not save_variant),
        checkpoint=JobCheckpoint(*job_owner) if job_owner else None)
    if save_variant:
        return 'variant_saved'
    return "text_only" if embedding_error else "processed"


def failure_reason(exc: Exception) -> str:
    """Operator diagnostics without provider bodies, SQL parameters, or text."""
    if isinstance(exc, (IngestionError, ProviderError, ProcessorError)):
        return str(exc)
    if isinstance(exc, ProcessorClientError):
        cause = exc.__cause__
        if isinstance(cause, urllib.error.HTTPError):
            return f"Processor request failed (HTTP {cause.code})"
        return "Processor unavailable or returned an invalid response"
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
            counts[status] = counts.get(status, 0) + 1
            report(f"{status}: {relative}")
    report("Batch completed: " + ", ".join(f"{name}={count}" for name, count in counts.items()))
    # An error status means all files were visited but some need attention.
    return counts["failed"] > 0 or counts.get("text_only", 0) > 0




def process_derived_file(store, provider, extractor, settings, job, worker, index, current, path, *, report, ocr=None):
    payload = job["payload"]
    steps = current.setdefault("steps", {})
    if payload["operation"] not in {"embed", "process"} and steps.get("extraction") != "done":
        current["current_step"] = "extraction"
        store.update_processing_item(job["id"], worker, index, current)
        ingest_file(store, provider, extractor, settings.source_root, path, ocr=ocr,
            force=payload["operation"] in {"extract", "reprocess"}, embed=False, job_owner=(job["id"], worker))
        steps["extraction"] = "done"
        store.update_processing_item(job["id"], worker, index, current)
    fid = "sha256-" + hashlib.sha256(path.read_bytes()).hexdigest()
    doc = store.document(fid)
    if not doc or not doc["active"] or doc["source_relpath"] != current["path"]:
        raise IngestionError("Source no longer matches its indexed document. Extract it before processing.")
    derived_outputs(store, settings, provider, job, worker, index, current, doc, report=report)
    if payload["embed"] and steps.get("embedding") != "done":
        current["current_step"] = "embedding"
        store.update_processing_item(job["id"], worker, index, current)
        rows = store.document_chunks(fid)
        if not rows:
            raise IngestionError("No text chunks are available for embeddings")
        for offset in range(0, len(rows), 32):
            batch = rows[offset:offset+32]
            vectors = provider.embed(payload["embedding_model"], [row["text"] for row in batch])
            if len(vectors) != len(batch):
                raise IngestionError("Embedding service returned the wrong number of vectors")
            for row, vector in zip(batch, vectors):
                row["embedding"] = vector
        from osii.processor_sdk import (Capability, ProcessorDescriptor, ProcessorKind,
            EmbeddingRequest, EmbeddingInput, EmbeddingResponse, EmbeddingVector)
        from osii.domain.storage.commits import text_digest
        producer = ProcessorDescriptor(name="core.openai-compatible-embedder", version="1",
            display_name="Configured embedding endpoint", description="Core model-provider adapter",
            kind=ProcessorKind.EMBEDDER, capabilities=Capability(scope_types=["object"]))
        request = EmbeddingRequest(request_id=identifier(), config={"model": payload["embedding_model"]},
            inputs=[EmbeddingInput(id=row["chunk_id"], text=row["text"]) for row in rows])
        response = EmbeddingResponse(request_id=request.request_id, processor=producer,
            model=payload["embedding_model"], vectors=[EmbeddingVector(id=row["chunk_id"],
                vector=row["embedding"], dimensions=len(row["embedding"])) for row in rows],
            metadata={"endpoint_type": "openai-compatible", "provider_id": settings.endpoints()["embedding"].base_url})
        steps["embedding"] = "done"
        PostgresProcessingCommitter(store.engine).commit(ProcessingCommit(
            f"{job['id']}:{index}:embedding", fid, request, response, producer,
            input_revision=InputRevision(fid, doc["metadata"]["primary_extraction_id"], text_digest(doc["text"])),
            chunks=tuple(rows), provenance={"run_id": job["id"]}),
            checkpoint=JobCheckpoint(job["id"], worker, index, current))
    current["current_step"] = "finished"

def process_plan(store: PostgresStore, provider, extractor, settings: Settings,
                 job: dict, worker: str, stopping: threading.Event, *, report, ocr=None) -> bool:
    from osii.server.intake import source_file, configuration_stamp
    payload = job["payload"]
    if payload["configuration_stamp"] != configuration_stamp(store, settings):
        raise IngestionError("Model or processor settings changed. Stage a new plan with the current settings.")
    for index, item in enumerate(payload["items"]):
        if store.checkpoint(job["id"], worker) != "running":
            return False
        if stopping.is_set():
            # Stop at a file boundary. A restart resumes uncommitted work.
            raise IngestionError("Worker stopped; completed files are retained. Retry this run to continue.")
        if item["status"] == "done":
            continue
        started = now()
        current = {**item, "status": "running", "started_at": started.isoformat(), "finished_at": None, "duration_seconds": None, "error": None}
        if store.checkpoint(job["id"], worker, item=current, index=index) != "running":
            return False
        report("processing: " + item["path"])
        try:
            inventory_member = next((m for m in payload.get('inventory_members', []) if m['source_relpath'] == item['path']), None)
            if inventory_member:
                from osii.persistence.inventory import PostgresInventory
                PostgresInventory(store, settings.source_root).verify_member(inventory_member)
            planned_extractor = (SelectedExtractor(store, settings, provider, payload['extractor'], payload.get('extractor_config',{}), job['id'],worker)
                                 if payload.get('extractor') else extractor)
            path = source_file(settings.source_root, item["path"])
            stat = path.stat()
            if stat.st_size != item["size_bytes"] or stat.st_mtime_ns != item["mtime_ns"]:
                raise IngestionError("Source changed after staging. Stage a new plan to review it.")
            if payload.get("synthesizer") or payload.get("enricher"):
                process_derived_file(store, provider, planned_extractor, settings, job, worker, index, current, path, report=report, ocr=ocr)
                result = "processed"
            elif payload["operation"] in {"embed", "process"}:
                fid = "sha256-" + hashlib.sha256(path.read_bytes()).hexdigest()
                doc = store.document(fid)
                if not doc or not doc["active"] or doc["source_relpath"] != item["path"]:
                    raise IngestionError("Source no longer matches its indexed document. Extract it before embedding.")
                rows = store.document_chunks(fid)
                if not rows:
                    raise IngestionError("No text chunks are available; extract this file before embedding.")
                for offset in range(0, len(rows), 32):
                    batch = rows[offset:offset+32]
                    vectors = provider.embed(payload["embedding_model"], [row["text"] for row in batch])
                    if len(vectors) != len(batch):
                        raise IngestionError("Embedding service returned the wrong number of vectors")
                    for row, vector in zip(batch, vectors):
                        row["embedding"] = vector
                store.replace_embeddings(fid, rows, payload["embedding_model"], job_owner=(job["id"], worker))
                result = "embedded"
            else:
                result = ingest_file(store, provider, planned_extractor, settings.source_root, path, ocr=ocr,
                    force=payload["operation"] in {"extract", "reprocess"}, embed=payload["embed"], job_owner=(job["id"], worker), save_variant=payload.get("extraction_policy")=="save_variant")
            if inventory_member:
                from sqlalchemy import select
                from osii.persistence.postgres import documents
                inventory = PostgresInventory(store, settings.source_root)
                inventory.verify_member(inventory_member)
                with store.engine.connect() as connection:
                    linked = connection.execute(select(documents.c.file_id).where(documents.c.active, documents.c.source_relpath == item['path'])).scalar()
                if linked:
                    inventory.link(inventory_member, linked, job, worker)
            current.update(status="done", result=result)
            if result == "text_only":
                current.update(status="error", error="Text saved, but embedding failed. Keyword search remains available; retry embeddings.")
        except OperationalError:
            raise
        except Exception as exc:
            current.update(status="error", error=failure_reason(exc))
        current.update(finished_at=now().isoformat(), duration_seconds=(now()-started).total_seconds())
        item.update(current)
        report_status = current.get("error") or current.get("result", "done")
        report(f"{current['status']}: {item['path']}: {report_status}")
        if store.checkpoint(job["id"], worker, item=current, index=index) != "running":
            return False
    return any(item["status"] == "error" for item in payload["items"])


def run(settings: Settings | None = None) -> None:
    settings = settings or Settings.environment()
    store = PostgresStore(settings.database_url)
    store.ready()
    provider = ConfiguredModelProvider(ModelConnections(store, settings))
    extractor = ProcessorClient(settings.extractor_url, timeout=120)
    ocr = ProcessorClient(settings.ocr_url, timeout=180) if settings.ocr_url else None
    worker, stopping = identifier(), threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stopping.set())
    last_seen = 0.0
    while not stopping.is_set():
        if time.monotonic() - last_seen > 10:
            store.save_setting("worker_status", {"last_seen": now().isoformat()})
            last_seen = time.monotonic()
        # Acquire the single-writer lock BEFORE claiming; a second worker must
        # not lease another run while waiting behind the current writer.
        with store.engine.connect() as lock:
            if not lock.execute(text("SELECT pg_try_advisory_lock(914035)")).scalar():
                stopping.wait(1)
                continue
            try:
                job = store.claim(worker)
                if not job:
                    stopping.wait(1)
                    continue
                finished = threading.Event()
                def heartbeat():
                    while not finished.wait(10):
                        store.heartbeat(job["id"], worker)
                        store.save_setting("worker_status", {"last_seen": now().isoformat()})
                thread = threading.Thread(target=heartbeat, daemon=True)
                thread.start()
                logs, failed, reschedule = list(job["logs"]), False, False
                def report(entry: str) -> None:
                    if not store.progress(job["id"], worker, entry):
                        raise IngestionError("Worker no longer owns this job; processing stopped.")
                    logs.append(entry)
                try:
                    if job["kind"] == "inventory_scan":
                        from osii.server.inventory import execute_scan
                        failed, pending = execute_scan(store, settings, job, worker, stopping, report)
                        reschedule = bool(pending and not failed)
                    elif job["kind"] == "tool":
                        from osii.server.library_tools import execute
                        reschedule = execute(store, settings, provider, job, worker, stopping, report)
                    elif job["kind"] == "plan":
                        failed = process_plan(store, provider, extractor, settings, job, worker, stopping, report=report, ocr=ocr)
                    else:
                        failed = ingest_batch(store, provider, extractor, settings.source_root,
                            report=report, stopping=stopping, ocr=ocr, force=bool(job["payload"].get("force")),
                            source_directory=job["payload"].get("source_directory", "."))
                except Exception as exc:
                    logs.append("Batch stopped: " + failure_reason(exc))
                    failed = True
                finally:
                    finished.set()
                    thread.join(timeout=2)
                    store.finish(job["id"], worker, logs, failed, reschedule=reschedule)
            finally:
                lock.execute(text("SELECT pg_advisory_unlock(914035)"))


if __name__ == "__main__":
    run()
