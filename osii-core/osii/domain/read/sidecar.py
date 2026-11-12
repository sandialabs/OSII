"""Sidecar implementation of LibraryReader. No directory creation or migration."""
from __future__ import annotations

import json
import mimetypes
from contextlib import closing
from pathlib import Path
import sqlite3
import tomllib
from typing import Callable

from .contracts import (ArtifactContent, ArtifactRecord, DocumentRecord, Page,
    ReadScope, RepresentationRecord, cursor_decode, cursor_encode, folder_contains,
    page_size, scope_context, representation_segments)


class SidecarLibraryReader:
    def __init__(self, root: Path, *, product_reader: Callable[[Path], dict] | None = None):
        self.root = Path(root).resolve()
        self.product_reader = product_reader

    def _path(self, *parts: str) -> Path:
        path = self.root.joinpath(*parts).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Read reference escapes the library")
        return path

    def _object(self, file_id: str) -> Path:
        if not file_id or file_id in {".", ".."} or any(c in file_id for c in "/\\\0"):
            raise ValueError("Invalid document identifier")
        return self._path("objects", file_id)

    @staticmethod
    def _toml(path: Path) -> dict:
        return tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}

    @staticmethod
    def _json(path: Path, default=None):
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default

    def get_document(self, file_id: str) -> DocumentRecord | None:
        self._object(file_id)
        meta = self._toml(self._path("objects", file_id, "meta.toml"))
        if not meta:
            return None
        record = meta.get("file", {})
        return DocumentRecord(file_id, str(record.get("source_relpath", "")),
            str(record.get("filename", "")), record.get("mime"), record.get("size_bytes"),
            meta.get("hash", {}).get("sha256"), meta)

    def _members(self, scope: ReadScope) -> set[str] | None:
        if scope.kind != "collection":
            return None
        if scope.identifier in {".", ".."} or any(c in scope.identifier for c in "/\\\0"):
            raise ValueError("Invalid collection identifier")
        path = self._path("collections", scope.identifier, "members.jsonl")
        return {str(json.loads(line)["file_id"]) for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()} if path.is_file() else set()

    def list_documents(self, scope: ReadScope = ReadScope(), *, limit: int = 100,
                       cursor: str | None = None) -> Page[DocumentRecord]:
        limit = page_size(limit)
        context = scope_context(scope)
        after = cursor_decode(cursor, context, 2)
        members = self._members(scope)
        catalog = self.root / "state" / "catalog.sqlite3"
        if catalog.is_file():
            # Open the derived catalog read-only. Initialization/recovery belongs
            # to the existing composition, never to a query interface.
            with closing(sqlite3.connect(catalog.as_uri() + "?mode=ro", uri=True)) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("BEGIN")
                terms, values = ["status IN ('done', 'partial')"], []
                if scope.kind == "object":
                    terms.append("file_id = ?")
                    values.append(scope.identifier)
                elif scope.kind == "folder" and scope.identifier.strip("/") not in {"", "."}:
                    prefix = scope.identifier.strip("/")
                    terms.append("source_relpath COLLATE BINARY >= ? AND source_relpath COLLATE BINARY < ?")
                    values.extend([prefix + "/", prefix + "0"])
                elif members is not None:
                    # A temporary table bounds parameters for large collections.
                    conn.execute("CREATE TEMP TABLE selected_members(id TEXT PRIMARY KEY)")
                    conn.executemany("INSERT INTO selected_members VALUES (?)", ((x,) for x in members))
                    terms.append("file_id IN (SELECT id FROM selected_members)")
                where = " AND ".join(terms)
                total = conn.execute(f"SELECT COUNT(*) FROM documents WHERE {where}", values).fetchone()[0]
                if after:
                    where += " AND (source_relpath COLLATE BINARY, file_id COLLATE BINARY) > (?, ?)"
                    values.extend(after)
                rows = conn.execute(f"SELECT * FROM documents WHERE {where} ORDER BY source_relpath COLLATE BINARY, file_id COLLATE BINARY LIMIT ?", (*values, limit + 1)).fetchall()
                items = tuple(DocumentRecord(row["file_id"], row["source_relpath"], row["filename"], row["mime"], row["size_bytes"], row["sha256"]) for row in rows[:limit])
                more = len(rows) > limit
        else:
            # Compatibility for portable stores without a catalog: bounded
            # results, but a full metadata scan. No catalog is created here.
            import heapq
            objects = self.root / "objects"
            total = 0
            def records():
                nonlocal total
                for obj in objects.iterdir() if objects.is_dir() else ():
                    if not obj.is_dir():
                        continue
                    record = self.get_document(obj.name)
                    provenance = self._toml(obj / "provenance.toml")
                    if record is None or provenance.get("provenance", {}).get("status", "unknown") not in {"done", "partial"}:
                        continue
                    if scope.kind == "object" and record.file_id != scope.identifier:
                        continue
                    if scope.kind == "folder" and not folder_contains(record.source_relpath, scope.identifier):
                        continue
                    if members is not None and record.file_id not in members:
                        continue
                    total += 1
                    if after is None or (record.source_relpath, record.file_id) > tuple(after):
                        yield record
            rows = heapq.nsmallest(limit + 1, records(), key=lambda item: (item.source_relpath, item.file_id))
            items, more = tuple(rows[:limit]), len(rows) > limit
        next_cursor = cursor_encode(context, [items[-1].source_relpath, items[-1].file_id]) if more else None
        return Page(items, total, next_cursor)

    def representation_path(self, file_id: str, representation_id: str = "preferred") -> Path:
        """Local compatibility URL mapping; not part of LibraryReader."""
        obj = self._object(file_id)
        index = self._json(obj / "extractions" / "index.json", {})
        if representation_id == "preferred":
            if (obj / "edited_text.json").is_file():
                return self._path("objects", file_id, "edited_text.json")
            representation_id = index.get("primary_id") or "canonical"
        if representation_id in {"canonical", "edited"}:
            return self._path("objects", file_id, "text.txt" if representation_id == "canonical" else "edited_text.json")
        if representation_id not in {item.get("id") for item in index.get("variants", [])}:
            return obj / "extractions" / "__missing__" / "text.txt"
        if representation_id in {".", ".."} or any(c in representation_id for c in "/\\\0"):
            raise ValueError("Invalid representation identifier")
        return self._path("objects", file_id, "extractions", representation_id, "text.txt")

    def get_representation(self, file_id: str, representation_id: str = "preferred") -> RepresentationRecord | None:
        if self.get_document(file_id) is None:
            return None
        obj = self._object(file_id)
        path = self.representation_path(file_id, representation_id)
        if not path.is_file():
            return None
        if path.name == "edited_text.json":
            # Preserve the current segment-override semantics without invoking
            # legacy helpers that initialize stores or archive extractions.
            overrides = {row["id"]: row["text"] for row in self._json(path, {}).get("segments", [])}
            records = self._manifest(obj / "manifest.jsonl")
            parts = []
            for row in records:
                if row.get("kind") != "text":
                    continue
                text = overrides.get(row.get("id"))
                if text is None:
                    source = self._path("objects", file_id, str(row.get("path", "text.txt")))
                    if not source.is_file():
                        continue
                    text = source.read_text(encoding="utf-8")
                    span = row.get("span") or {}
                    if isinstance(span.get("char_start"), int) and isinstance(span.get("char_end"), int):
                        text = text[span["char_start"]:span["char_end"]]
                parts.append(text)
            return RepresentationRecord("edited", file_id, "\n\n".join(parts).strip(), kind="edited_text")
        identity = path.parent.name if path.parent != obj else "canonical"
        text = path.read_text(encoding="utf-8")
        return RepresentationRecord(identity, file_id, text,
            representation_segments(text, [row for row in self._manifest(path.parent / "manifest.jsonl") if row.get("kind") == "text"]),
            provenance=self._toml(path.parent / "provenance.toml"))

    @staticmethod
    def _manifest(path: Path) -> list[dict]:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.is_file() else []

    def _artifact(self, file_id: str, path: Path) -> ArtifactRecord:
        obj = self._object(file_id)
        payload = {}
        if path.suffix == ".json":
            if self.product_reader is not None:
                payload = self.product_reader(path).get("data")
            elif path.stat().st_size <= 5 * 1024 * 1024:
                payload = self._json(path, {})
        payload = payload if isinstance(payload, dict) else {}
        return ArtifactRecord(path.relative_to(obj).as_posix(), file_id,
            str(payload.get("artifact_type") or "artifact"), mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            str(payload.get("title") or path.name))

    def _product_data(self, path: Path) -> bytes | None:
        if self.product_reader is None or path.suffix not in {".json", ".txt", ".md"}:
            return None
        data = self.product_reader(path).get("data")
        if data is None:
            return None
        if path.suffix == ".json":
            return json.dumps(data, ensure_ascii=False).encode("utf-8")
        return str(data.get("text" if path.suffix == ".txt" else "markdown", "")).encode("utf-8")

    def list_artifacts(self, file_id: str, *, limit: int = 100, cursor: str | None = None) -> Page[ArtifactRecord]:
        limit = page_size(limit)
        context = json.dumps(["artifacts", file_id])
        after = cursor_decode(cursor, context, 1)
        if self.get_document(file_id) is None:
            return Page((), 0)
        obj = self._object(file_id)
        paths = []
        for name in ("artifacts", "enrichments", "syntheses"):
            base = obj / name
            if base.is_dir():
                paths.extend(path for path in base.rglob("*") if path.is_file()
                    and not any(part.startswith(".") for part in path.relative_to(base).parts)
                    and not path.name.endswith(".meta.json"))
                if self.product_reader is not None:
                    for manifest in base.glob(".history/*/manifest.json"):
                        record = self._json(manifest, {})
                        name = record.get("filename")
                        if record.get("current") and isinstance(name, str) and Path(name).name == name:
                            candidate = base / name
                            if candidate not in paths:
                                paths.append(candidate)
        if (obj / "synth.txt").is_file():
            paths.append(obj / "synth.txt")
        rows = []
        for path in paths:
            path = self._path(str(path.relative_to(self.root)))
            if not path.is_relative_to(obj):
                raise ValueError("Artifact escapes its document")
            if self.product_reader is not None and path.suffix in {".json", ".txt", ".md"} and self.product_reader(path).get("data") is None:
                continue
            if not path.is_file() and self.product_reader is not None:
                data = self._product_data(path)
                if data is None:
                    continue
                payload = json.loads(data) if path.suffix == ".json" else {}
                rows.append(ArtifactRecord(path.relative_to(obj).as_posix(), file_id,
                    str(payload.get("artifact_type") or "artifact"), mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                    str(payload.get("title") or path.name)))
            else:
                rows.append(self._artifact(file_id, path))
        rows.sort(key=lambda row: row.artifact_id)
        total = len(rows)
        if after:
            rows = [row for row in rows if row.artifact_id > after[0]]
        items = tuple(rows[:limit])
        return Page(items, total, cursor_encode(context, [items[-1].artifact_id]) if len(rows) > limit else None)

    def get_artifact(self, file_id: str, artifact_id: str, *, max_bytes: int | None = 5 * 1024 * 1024) -> ArtifactContent | None:
        if max_bytes is not None and max_bytes < 0:
            raise ValueError("max_bytes must be nonnegative")
        if not artifact_id or Path(artifact_id).is_absolute():
            raise ValueError("Invalid artifact identifier")
        if self.get_document(file_id) is None:
            return None
        obj = self._object(file_id)
        path = self._path("objects", file_id, artifact_id)
        if not path.is_relative_to(obj) or any(part.startswith(".") for part in Path(artifact_id).parts):
            raise ValueError("Invalid artifact identifier")
        if Path(artifact_id).parts[0] not in {"artifacts", "enrichments", "syntheses", "synth.txt"} or path.name.endswith(".meta.json"):
            return None
        data = self._product_data(path)
        if data is None:
            if self.product_reader is not None and path.suffix in {".json", ".txt", ".md"}:
                return None
            if not path.is_file():
                return None
            with path.open("rb") as handle:
                data = handle.read() if max_bytes is None else handle.read(max_bytes + 1)
        if max_bytes is not None and len(data) > max_bytes:
            raise ValueError("Artifact exceeds the requested byte limit")
        if path.is_file():
            artifact = self._artifact(file_id, path)
        else:
            payload = json.loads(data) if path.suffix == ".json" else {}
            artifact = ArtifactRecord(artifact_id, file_id, str(payload.get("artifact_type") or "artifact"),
                mimetypes.guess_type(path.name)[0] or "application/octet-stream", str(payload.get("title") or path.name))
        return ArtifactContent(artifact, data)
