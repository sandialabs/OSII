"""Preferred-text edits: immutable extraction evidence plus revisioned overrides."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Protocol

from .authoring import AuthoringConflict


@dataclass(frozen=True)
class TextEdit:
    revision: str | None
    segments: tuple[dict, ...]
    text: str | None
    state_revision: str | None = None


class TextAuthoring(Protocol):
    def get(self, file_id: str) -> TextEdit: ...
    def save(
        self,
        file_id: str,
        segments: list[dict] | None,
        *,
        expected_revision: str | None,
    ) -> TextEdit: ...


def edited_material(canonical, segments):
    valid = {segment.segment_id: segment for segment in canonical.segments}
    override = {}
    for row in segments:
        if (
            not isinstance(row, dict)
            or row.get("id") not in valid
            or not isinstance(row.get("text"), str)
        ):
            raise ValueError("Each edit needs a known canonical segment ID and text")
        if row["id"] in override:
            raise ValueError("Edited segment IDs must be unique")
        override[row["id"]] = row["text"]
    normalized = tuple({"id": key, "text": value} for key, value in override.items())
    text = "\n\n".join(
        override.get(segment.segment_id, segment.text) for segment in canonical.segments
    ).strip()
    return normalized, text


def edit_revision(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


class SidecarTextAuthoring:
    def __init__(self, root):
        self.root = root

    def get(self, file_id):
        from osii.domain.read.sidecar import SidecarLibraryReader

        reader = SidecarLibraryReader(self.root)
        if reader.get_document(file_id) is None:
            raise KeyError("Document not found")
        path = reader._path("objects", file_id, "edited_text.json")
        value = reader._json(path)
        if value is None:
            return TextEdit(None, (), None)
        return TextEdit(
            value.get("revision") or edit_revision(value),
            tuple(value.get("segments", [])),
            reader.get_representation(file_id, "edited").text,
        )

    def save(self, file_id, segments, *, expected_revision):
        from osii.domain.read.sidecar import SidecarLibraryReader
        from osii.domain.artifacts.products import _lock
        from .atomic import atomic_write_text
        from datetime import UTC, datetime
        import uuid

        reader = SidecarLibraryReader(self.root)
        with _lock(self.root):
            current = self.get(file_id)
            if current.revision != expected_revision:
                raise AuthoringConflict("Preferred text changed; reload before editing")
            canonical = reader.get_representation(file_id, "canonical")
            if canonical is None:
                raise KeyError("Canonical text not found")
            normalized, text = (
                edited_material(canonical, segments)
                if segments is not None
                else ((), None)
            )
            path = reader._path("objects", file_id, "edited_text.json")
            history_path = reader._path("objects", file_id, "edited_text.history.json")
            history = reader._json(history_path, [])
            if current.revision is not None and not any(
                row["id"] == current.revision for row in history
            ):
                history.append(
                    {
                        "id": current.revision,
                        "segments": current.segments,
                        "text": current.text,
                        "origin": "imported",
                    }
                )
            revision = uuid.uuid4().hex
            history.append(
                {
                    "id": revision,
                    "parent": current.revision,
                    "segments": normalized,
                    "text": text,
                    "created_at": datetime.now(UTC).isoformat(),
                    "origin": "human",
                }
            )
            atomic_write_text(history_path, json.dumps(history, ensure_ascii=False))
            if segments is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write_text(
                    path,
                    json.dumps(
                        {"revision": revision, "segments": normalized},
                        ensure_ascii=False,
                    ),
                )
        from osii.domain.artifacts.artifact_staleness import mark_artifacts_stale

        mark_artifacts_stale(self.root, file_id, embeddings=True, search_chunks=True)
        return self.get(file_id)


def text_state_revision(text, metadata):
    """Changes on canonical replacement, edits and restores; unrelated metadata is ignored."""
    history = metadata.get("edited_text_history", [])
    return edit_revision({"canonical": metadata.get("primary_extraction_id") or hashlib.sha256(text.encode()).hexdigest(),
                          "last_edit": history[-1]["id"] if history else None,
                          "edit": (metadata.get("edited_representation") or {}).get("revision")})


class PostgresTextAuthoring:
    def __init__(self, engine):
        self.engine = engine

    def get(self, file_id):
        from sqlalchemy import text

        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT text,metadata FROM documents WHERE file_id=:id AND active"),
                {"id": file_id},
            ).first()
        if row is None:
            raise KeyError("Document not found")
        edited = row[1].get("edited_representation")
        state = text_state_revision(row[0], row[1])
        return (
            TextEdit(edited["revision"], tuple(edited["segments"]), edited["text"], state)
            if edited
            else TextEdit(None, (), None, state)
        )

    def save(self, file_id, segments, *, expected_revision, expected_state=None, expected_extraction_id=None):
        from sqlalchemy import text
        from osii.domain.read.contracts import (
            RepresentationRecord,
            representation_segments,
        )
        from datetime import UTC, datetime
        import uuid

        with self.engine.begin() as conn:
            row = (
                conn.execute(
                    text(
                        "SELECT text,metadata FROM documents WHERE file_id=:id AND active FOR UPDATE"
                    ),
                    {"id": file_id},
                )
                .mappings()
                .first()
            )
            if row is None:
                raise KeyError("Document not found")
            metadata = dict(row["metadata"])
            if expected_state is not None and text_state_revision(row["text"], metadata) != expected_state:
                raise AuthoringConflict("Text or extraction changed; reload before editing")
            if expected_extraction_id is not None:
                primary = metadata.get("primary_extraction_id") or conn.execute(text("SELECT id FROM extractions WHERE file_id=:id ORDER BY created_at DESC,id LIMIT 1"), {"id": file_id}).scalar()
                if primary != expected_extraction_id:
                    raise AuthoringConflict("Extraction changed; reload before editing")
            old = metadata.get("edited_representation")
            if (old or {}).get("revision") != expected_revision:
                raise AuthoringConflict("Preferred text changed; reload before editing")
            canonical = RepresentationRecord(
                "canonical",
                file_id,
                row["text"],
                representation_segments(row["text"], metadata.get("segments", [])),
            )
            normalized, content = (
                edited_material(canonical, segments)
                if segments is not None
                else ((), None)
            )
            revision = uuid.uuid4().hex
            history = metadata.setdefault("edited_text_history", [])
            if old and not any(item["id"] == old["revision"] for item in history):
                history.append({"id": old["revision"], **old, "origin": "imported"})
            history.append(
                {
                    "id": revision,
                    "parent": expected_revision,
                    "segments": normalized,
                    "text": content,
                    "origin": "human",
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )
            if segments is None:
                metadata.pop("edited_representation", None)
            else:
                metadata["edited_representation"] = {
                    "revision": revision,
                    "segments": normalized,
                    "text": content,
                }
            metadata["stale"] = {"embeddings": True, "search_chunks": True, "syntheses": True, "enrichments": True}
            metadata["stale"]["search_chunks"] = False
            conn.execute(
                text(
                    "UPDATE documents SET metadata=CAST(:meta AS jsonb),updated_at=CURRENT_TIMESTAMP WHERE file_id=:id"
                ),
                {"id": file_id, "meta": json.dumps(metadata, ensure_ascii=False)},
            )
            # Old offsets/vectors cannot describe human-edited text.
            conn.execute(text("DELETE FROM chunks WHERE file_id=:id"), {"id": file_id})
            from osii.indexing.chunking import chunk_saved_text

            preferred = content if segments is not None else row["text"]
            grounding = (
                []
                if segments is not None
                else [
                    {
                        "id": s.segment_id,
                        "char_start": s.char_start,
                        "char_end": s.char_end,
                        "source_origin": s.source_origin,
                    }
                    for s in canonical.segments
                ]
            )
            for chunk in chunk_saved_text(file_id, preferred, grounding):
                conn.execute(
                    text("""INSERT INTO chunks(chunk_id,file_id,text,char_start,char_end,source_origin)
                    VALUES (:chunk_id,:file_id,:text,:char_start,:char_end,CAST(:source_origin AS jsonb))"""),
                    {**chunk, "source_origin": json.dumps(chunk["source_origin"])},
                )
            conn.execute(
                text("UPDATE datasets SET revision=revision+1 WHERE id='shared'")
            )
        return self.get(file_id)
