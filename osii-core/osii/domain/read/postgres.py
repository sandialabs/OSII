"""Read-only adapter over the existing hosted schema; no schema/bootstrap writes.

SQLAlchemy and psycopg are optional. Importing the shared contracts or sidecar
adapter does not import either dependency. The owning composition supplies an
engine and the authenticated collection owner, never a filesystem fallback.
"""
from __future__ import annotations

from contextlib import contextmanager
import base64
import json
from typing import TYPE_CHECKING

from .contracts import (ArtifactContent, ArtifactRecord, DocumentRecord, Page,
    ReadScope, RepresentationRecord, cursor_decode, cursor_encode, page_size, scope_context, representation_segments)

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine


class PostgresLibraryReader:
    def __init__(self, engine: Engine, *, actor_id: str | None = None):
        if engine.dialect.name != "postgresql":
            raise ValueError("PostgresLibraryReader requires PostgreSQL")
        self.engine, self.actor_id = engine, actor_id

    @contextmanager
    def _connection(self):
        from sqlalchemy import text
        with self.engine.begin() as connection:
            connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            yield connection

    @staticmethod
    def _execute(connection, statement, values):
        from sqlalchemy import text
        return connection.execute(text(statement), values)

    @staticmethod
    def _document(row) -> DocumentRecord:
        return DocumentRecord(row["file_id"], row["source_relpath"], row["filename"],
            row["media_type"], row["size_bytes"], row["sha256"], row["metadata"])

    def list_documents(self, scope: ReadScope = ReadScope(), *, limit: int = 100,
                       cursor: str | None = None) -> Page[DocumentRecord]:
        limit = page_size(limit)
        context = scope_context(scope)
        after = cursor_decode(cursor, context, 2)
        where, values = "d.active", {"identity": scope.identifier, "actor": self.actor_id}
        if scope.kind == "object":
            where += " AND d.file_id = :identity"
        elif scope.kind == "folder" and scope.identifier.strip("/") not in {"", "."}:
            prefix = scope.identifier.strip("/")
            where += ' AND d.source_relpath COLLATE "C" >= :lower AND d.source_relpath COLLATE "C" < :upper'
            values.update(lower=prefix + "/", upper=prefix + "0")
        elif scope.kind == "collection":
            where += """ AND EXISTS (SELECT 1 FROM collections c WHERE c.id = :identity
                AND (c.visibility = 'shared' OR c.owner_id = :actor)
                AND c.members ? d.file_id)"""
        with self._connection() as conn:
            total = self._execute(conn, f"SELECT count(*) FROM documents d WHERE {where}", values).scalar_one()
            if after:
                where += ' AND (d.source_relpath COLLATE "C", d.file_id COLLATE "C") > (:path, :file_id)'
                values.update(path=after[0], file_id=after[1])
            values["limit"] = limit + 1
            rows = self._execute(conn, f"""SELECT d.file_id, d.source_relpath, d.filename,
                d.media_type, d.size_bytes, d.sha256, d.metadata FROM documents d
                WHERE {where} ORDER BY d.source_relpath COLLATE "C", d.file_id COLLATE "C" LIMIT :limit""", values).mappings().all()
        items = tuple(self._document(row) for row in rows[:limit])
        return Page(items, total, cursor_encode(context, [items[-1].source_relpath, items[-1].file_id]) if len(rows) > limit else None)

    def get_document(self, file_id: str) -> DocumentRecord | None:
        with self._connection() as conn:
            row = self._execute(conn, """SELECT file_id, source_relpath, filename,
                media_type, size_bytes, sha256, metadata FROM documents WHERE file_id=:id AND active""", {"id": file_id}).mappings().first()
        return self._document(row) if row else None

    def get_representation(self, file_id: str, representation_id: str = "preferred") -> RepresentationRecord | None:
        with self._connection() as conn:
            doc = self._execute(conn, "SELECT text, metadata FROM documents WHERE file_id=:id AND active", {"id": file_id}).mappings().first()
            if not doc:
                return None
            selected = representation_id
            if selected in {"preferred", "canonical"} or selected == doc["metadata"].get("primary_extraction_id"):
                selected = doc["metadata"].get("primary_extraction_id")
                row = self._execute(conn, """SELECT id, response FROM extractions WHERE file_id=:file_id
                    AND (CAST(:id AS text) IS NULL OR id=:id) ORDER BY created_at DESC, id LIMIT 1""", {"file_id": file_id, "id": selected}).mappings().first()
                content = doc["text"]
                segments = doc["metadata"].get("segments", [])
            else:
                row = self._execute(conn, "SELECT id, response FROM extractions WHERE file_id=:file_id AND id=:id", {"file_id": file_id, "id": selected}).mappings().first()
                if not row:
                    return None
                parts, segments, position = [], [], 0
                for item in row["response"].get("segments", []):
                    if parts:
                        position += 1
                    text = item.get("text", "")
                    segments.append({"id": item["id"], "char_start": position,
                        "char_end": position + len(text), "source_origin": item.get("source_origin", {})})
                    parts.append(text)
                    position += len(text)
                content = "\n".join(parts)
            if not row:
                return RepresentationRecord("canonical", file_id, content, representation_segments(content, segments))
            response = row["response"]
            processor = response.get("processor", {})
            return RepresentationRecord(row["id"], file_id, content, representation_segments(content, segments),
                provenance={"extractor": processor, "response_metadata": response.get("metadata", {})})

    @staticmethod
    def _artifact(row) -> ArtifactRecord:
        payload = row["payload"]
        data = payload.get("data", payload)
        data = data if isinstance(data, dict) else {}
        return ArtifactRecord(row["id"], row["file_id"],
            str(data.get("artifact_type") or row["kind"]), str(payload.get("media_type") or "application/json"),
            str(data.get("title") or ""), {"storage_kind": row["kind"], "provenance": payload.get("metadata", {})})

    def artifact_responses(self, file_id: str) -> list[dict]:
        """Preserve the existing unpaginated hosted HTTP envelope at its edge.

        New Core clients use list_artifacts/get_artifact. This compatibility
        mapping fetches existing response payloads in one query, not N+1 reads.
        """
        with self._connection() as conn:
            return [dict(row) for row in self._execute(conn, """SELECT a.* FROM artifacts a
                WHERE a.file_id=:id AND EXISTS (SELECT 1 FROM documents d WHERE d.file_id=a.file_id AND d.active)
                ORDER BY a.id COLLATE "C"
                """, {"id": file_id}).mappings()]

    def list_artifacts(self, file_id: str, *, limit: int = 100, cursor: str | None = None) -> Page[ArtifactRecord]:
        limit = page_size(limit)
        context = json.dumps(["artifacts", file_id])
        after = cursor_decode(cursor, context, 1)
        values = {"id": file_id, "after": after[0] if after else None, "limit": limit + 1}
        where = "a.file_id=:id AND EXISTS (SELECT 1 FROM documents d WHERE d.file_id=a.file_id AND d.active)"
        with self._connection() as conn:
            total = self._execute(conn, f"SELECT count(*) FROM artifacts a WHERE {where}", values).scalar_one()
            rows = self._execute(conn, f"""SELECT a.* FROM artifacts a WHERE {where}
                AND (CAST(:after AS text) IS NULL OR a.id COLLATE "C" > :after) ORDER BY a.id COLLATE "C" LIMIT :limit""", values).mappings().all()
        items = tuple(self._artifact(row) for row in rows[:limit])
        return Page(items, total, cursor_encode(context, [items[-1].artifact_id]) if len(rows) > limit else None)

    def get_artifact(self, file_id: str, artifact_id: str, *, max_bytes: int | None = 5 * 1024 * 1024) -> ArtifactContent | None:
        if max_bytes is not None and max_bytes < 0:
            raise ValueError("max_bytes must be nonnegative")
        with self._connection() as conn:
            row = self._execute(conn, """SELECT a.* FROM artifacts a WHERE a.file_id=:file_id AND a.id=:id
                AND EXISTS (SELECT 1 FROM documents d WHERE d.file_id=a.file_id AND d.active)""", {"file_id": file_id, "id": artifact_id}).mappings().first()
        if row is None:
            return None
        payload = row["payload"]
        if payload.get("data_base64") is not None:
            data = base64.b64decode(payload["data_base64"], validate=True)
        else:
            data = json.dumps(payload.get("data", payload), ensure_ascii=False).encode("utf-8")
        if max_bytes is not None and len(data) > max_bytes:
            raise ValueError("Artifact exceeds the requested byte limit")
        return ArtifactContent(self._artifact(row), data)
