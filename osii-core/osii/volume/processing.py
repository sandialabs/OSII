"""Bounded Processor API calls and canonical, revision-checked commits."""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import time
import urllib.request

from pydantic import ValidationError
from jsonschema import validators
from referencing import Registry

from osii.processor_sdk.client import ProcessorClient
from osii.processor_sdk.models import (
    DocumentInput,
    EnrichmentRequest,
    ExtractionRequest,
    ExtractionResponse,
    ScopeInput,
    SynthesisRequest,
)

from .models import ProcessRequest
from .scanner import InterruptedRun, check_owner, checked_path
from .store import VolumeStore, encode


class BoundedClient(ProcessorClient):
    def __init__(self, endpoint: str, max_output: int, timeout: float = 120):
        super().__init__(endpoint, timeout=timeout)
        self.max_output = max_output

    def _request(self, path: str, payload: bytes | None = None) -> dict:
        request = urllib.request.Request(
            self.base_url + path,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            data = response.read(self.max_output + 1)
        if len(data) > self.max_output:
            raise ValueError("Processor response exceeds configured size limit")
        return json.loads(data)

    def _post(self, path: str, payload_json: str) -> dict:
        return self._request(path, payload_json.encode())

    def _get(self, path: str) -> dict:
        return self._request(path)


def signature(info) -> tuple:
    # Windows file identifiers may exceed SQLite's signed 64-bit integer range.
    return (
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        str(info.st_dev),
        str(info.st_ino),
    )


def read_source(root: Path, entry: dict, limit: int) -> tuple[bytes, str]:
    path = checked_path(root, entry["path"])
    before = path.stat()
    if signature(before) != tuple(
        entry[k] for k in ("size_bytes", "mtime_ns", "ctime_ns", "device", "inode")
    ):
        raise ValueError("Source changed since inventory; scan again")
    if before.st_size > limit:
        raise ValueError("Source exceeds the configured per-file limit")
    # On POSIX open every component relative to held directory descriptors, so
    # a parent symlink swapped between validation and open cannot escape root.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    if os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW"):
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            parts = Path(entry["path"]).parts
            for part in parts[:-1]:
                child = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
                )
                os.close(directory)
                directory = child
            fd = os.open(parts[-1], flags, dir_fd=directory)
        finally:
            os.close(directory)
    else:
        fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        if signature(os.fstat(stream.fileno())) != signature(before):
            raise ValueError("Source changed before reading")
        content = stream.read(limit + 1)
        if len(content) > limit or signature(os.fstat(stream.fileno())) != signature(
            before
        ):
            raise ValueError("Source changed while reading")
    if signature(checked_path(root, entry["path"]).stat()) != signature(before):
        raise ValueError("Source changed while reading")
    return content, hashlib.sha256(content).hexdigest()


def _ensure_current(store, conn, run, owner, entry, root):
    check_owner(store, conn, run["id"], owner)
    current = conn.execute(
        "SELECT revision,status FROM entries WHERE id=?", (entry["id"],)
    ).fetchone()
    if current["revision"] != entry["revision"] or current["status"] != "present":
        raise ValueError("Source inventory revision changed")
    info = checked_path(root, entry["path"]).stat()
    if signature(info) != tuple(
        entry[k] for k in ("size_bytes", "mtime_ns", "ctime_ns", "device", "inode")
    ):
        raise ValueError("Source changed during processing; scan again")


def process(
    store: VolumeStore, run: dict, owner: str, stopping, client_factory=BoundedClient
) -> None:
    request = ProcessRequest.model_validate_json(run["payload"])
    client = client_factory(request.endpoint, request.max_output_bytes)
    client.timeout = min(120, request.max_seconds)
    descriptor = client.descriptor()
    kind = {
        "extract": "extractor",
        "ocr": "extractor",
        "synthesize": "synthesizer",
        "enrich": "enricher",
    }[request.stage]
    if descriptor.kind.value != kind:
        raise ValueError(f"Selected processor must be a {kind}")
    try:
        validator_type = validators.validator_for(descriptor.config_schema)
        validator_type.check_schema(descriptor.config_schema)
        validator_type(descriptor.config_schema, registry=Registry()).validate(
            request.config
        )
    except Exception as exc:
        raise ValueError(
            "Processor configuration does not match a valid, self-contained descriptor schema"
        ) from exc
    processor_key = hashlib.sha256(
        encode(
            {
                "descriptor": descriptor.model_dump(mode="json"),
                "config": request.config,
                "stage": request.stage,
                "endpoint": request.endpoint,
            }
        ).encode()
    ).hexdigest()
    while True:
        if stopping.is_set():
            raise InterruptedRun()
        with store.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            check_owner(store, conn, run["id"], owner)
            elapsed = conn.execute(
                "SELECT elapsed FROM runs WHERE id=?", (run["id"],)
            ).fetchone()[0]
            if elapsed >= request.max_seconds:
                raise ValueError(
                    "Run time budget reached; create a new bounded run for remaining work"
                )
            row = conn.execute(
                """SELECT e.*,w.revision AS selected_revision FROM work_items w
              JOIN entries e ON e.id=w.entry_id WHERE w.run_id=? AND w.status='pending'
              ORDER BY w.entry_id LIMIT 1""",
                (run["id"],),
            ).fetchone()
            if row is None:
                return
            entry = dict(row)
            conn.execute(
                "UPDATE work_items SET status='running',attempts=attempts+1 WHERE run_id=? AND entry_id=?",
                (run["id"], entry["id"]),
            )
        client.timeout = min(120, max(1, request.max_seconds - elapsed))
        started = time.monotonic()
        byte_count, text_chars, extraction_id = 0, 0, None
        root = Path(store.source(entry["source_id"])["root"])
        try:
            if (
                entry["selected_revision"] != entry["revision"]
                or entry["status"] != "present"
            ):
                raise ValueError(
                    "Selection is stale; create a new selection after scanning"
                )
            content, sha = read_source(root, entry, request.max_file_bytes)
            byte_count = len(content)
            document = DocumentInput(
                file_id="sha256-" + sha,
                filename=entry["name"],
                media_type=mimetypes.guess_type(entry["name"])[0]
                or "application/octet-stream",
                metadata={
                    "entry_id": entry["id"],
                    "source_id": entry["source_id"],
                    "path": entry["path"],
                    "revision": entry["revision"],
                },
            )
            # Only the known content-only native parser can share results across
            # names/locations. Arbitrary processors may interpret request metadata.
            cache_input = {
                "suffix": Path(entry["name"]).suffix.lower(),
                "media_type": document.media_type,
            }
            if descriptor.name != "local.native-text":
                cache_input["filename"] = document.filename
                cache_input["metadata"] = document.metadata
            content_processor_key = hashlib.sha256(
                (processor_key + encode(cache_input)).encode()
            ).hexdigest()
            response = None
            request_id = f"volume-{run['id']}-{entry['id']}"
            if request.stage in {"extract", "ocr"}:
                with store.connect() as conn:
                    cached = conn.execute(
                        "SELECT * FROM extractions WHERE sha256=? AND processor_key=?",
                        (sha, content_processor_key),
                    ).fetchone()
                if cached:
                    extraction_id, text_chars = cached["id"], len(cached["text"])
                    state = "reused" if text_chars else "needs_ocr"
                else:
                    document.content_base64 = base64.b64encode(content).decode("ascii")
                    response = client.extract(
                        ExtractionRequest(
                            request_id=request_id,
                            document=document,
                            config=request.config,
                        )
                    )
                    content_text = "\n".join(
                        segment.text for segment in response.segments
                    )
                    text_chars = len(content_text)
                    extraction_id = hashlib.sha256(
                        (sha + content_processor_key).encode()
                    ).hexdigest()
                    state = "done" if content_text.strip() else "needs_ocr"
            else:
                with store.connect() as conn:
                    extraction = conn.execute(
                        "SELECT * FROM extractions WHERE id=?",
                        (entry["extraction_id"],),
                    ).fetchone()
                if not extraction or extraction["sha256"] != sha:
                    raise ValueError(
                        "No current extraction; extract the selected source first"
                    )
                extraction_id = extraction["id"]
                document.text = extraction["text"]
                document.segments = ExtractionResponse.model_validate_json(
                    extraction["response"]
                ).segments
                # Bound scope size independently of source-file size.
                if len(document.text.encode("utf-8")) > request.max_output_bytes:
                    raise ValueError("Text exceeds the bounded processor scope size")
                scope = ScopeInput(
                    scope_type="object",
                    scope_id=str(entry["id"]),
                    documents=[document],
                    metadata={
                        "coverage": "one selected extracted document",
                        "extraction_id": extraction_id,
                    },
                )
                if request.stage == "synthesize":
                    response = client.synthesize(
                        SynthesisRequest(
                            request_id=request_id, scope=scope, config=request.config
                        )
                    )
                else:
                    response = client.enrich(
                        EnrichmentRequest(
                            request_id=request_id, scope=scope, config=request.config
                        )
                    )
                text_chars = len(document.text)
                state = "done"
            if response:
                if (
                    response.request_id != request_id
                    or response.processor != descriptor
                ):
                    raise ValueError(
                        "Processor response identity does not match its request and descriptor"
                    )
                encoded = response.model_dump_json()
                if len(encoded.encode()) > request.max_output_bytes:
                    raise ValueError("Processor response exceeds output limit")
                if request.stage == "synthesize":
                    for citation in response.citations:
                        if citation.file_id != document.file_id or (
                            citation.char_end is not None
                            and citation.char_end > len(document.text or "")
                        ):
                            raise ValueError(
                                "Processor returned an invalid source citation"
                            )
            with store.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                _ensure_current(store, conn, run, owner, entry, root)
                if request.stage in {"extract", "ocr"}:
                    if response:
                        conn.execute(
                            "INSERT INTO extractions(id,sha256,processor_key,response,text,created) VALUES(?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                            (
                                extraction_id,
                                sha,
                                content_processor_key,
                                encoded,
                                content_text,
                                time.time(),
                            ),
                        )
                    conn.execute(
                        "INSERT OR IGNORE INTO entry_extractions VALUES(?,?,?)",
                        (entry["id"], entry["revision"], extraction_id),
                    )
                    conn.execute(
                        "UPDATE entries SET extraction_id=? WHERE id=?",
                        (extraction_id, entry["id"]),
                    )
                else:
                    conn.execute(
                        "INSERT INTO products(run_id,entry_id,extraction_id,kind,response,created) VALUES(?,?,?,?,?,?) ON CONFLICT(run_id,entry_id) DO NOTHING",
                        (
                            run["id"],
                            entry["id"],
                            extraction_id,
                            request.stage,
                            encoded,
                            time.time(),
                        ),
                    )
                _finish_item(
                    conn,
                    run["id"],
                    entry["id"],
                    state,
                    started,
                    byte_count,
                    text_chars,
                    extraction_id,
                )
        except InterruptedRun:
            raise
        except (OSError, ValueError, RuntimeError) as exc:
            # Store bounded, sanitized diagnostics, never provider response bodies.
            reason = (
                str(exc)[:500]
                if isinstance(exc, ValueError)
                and not isinstance(exc, (json.JSONDecodeError, ValidationError))
                else f"Processing failed ({type(exc).__name__})"
            )
            with store.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                check_owner(store, conn, run["id"], owner)
                _finish_item(
                    conn,
                    run["id"],
                    entry["id"],
                    "error",
                    started,
                    byte_count,
                    0,
                    None,
                    reason,
                )
                conn.execute(
                    "INSERT INTO events(run_id,created,path,message) VALUES(?,?,?,?)",
                    (run["id"], time.time(), entry["path"], reason),
                )


def _finish_item(
    conn,
    run_id,
    entry_id,
    status,
    started,
    byte_count,
    text_chars,
    extraction_id,
    error=None,
):
    elapsed = time.monotonic() - started
    conn.execute(
        "UPDATE work_items SET status=?,error=?,seconds=?,bytes=?,text_chars=?,extraction_id=? WHERE run_id=? AND entry_id=?",
        (
            status,
            error,
            elapsed,
            byte_count,
            text_chars,
            extraction_id,
            run_id,
            entry_id,
        ),
    )
    conn.execute(
        "UPDATE runs SET completed=completed+1,bytes_read=bytes_read+?,elapsed=elapsed+?,updated=? WHERE id=?",
        (byte_count, elapsed, time.time(), run_id),
    )
