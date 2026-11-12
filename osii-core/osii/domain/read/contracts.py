"""Read-only library contracts shared by sidecar and hosted compositions.

Identifiers are logical, not filesystem paths. Authorization is supplied by the
composition before reading; a collection reader must also enforce visibility.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
import json
from typing import Any, Generic, Literal, Protocol, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class ReadScope:
    kind: Literal["root", "object", "folder", "collection"] = "root"
    identifier: str = ""

    def __post_init__(self):
        if self.kind not in {"root", "object", "folder", "collection"}:
            raise ValueError("Unsupported read scope")
        if self.kind != "root" and not self.identifier:
            raise ValueError("A scoped read requires an identifier")


@dataclass(frozen=True)
class Page(Generic[T]):
    items: tuple[T, ...]
    total: int
    next_cursor: str | None = None


@dataclass(frozen=True)
class DocumentRecord:
    file_id: str
    source_relpath: str
    filename: str
    media_type: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SegmentRecord:
    segment_id: str
    text: str
    char_start: int | None
    char_end: int | None
    source_origin: dict[str, Any] = field(default_factory=dict)


def representation_segments(text: str, records: list[dict]) -> tuple[SegmentRecord, ...]:
    segments = []
    for row in records:
        span = row.get("span") or row
        start, end = span.get("char_start"), span.get("char_end")
        valid_span = isinstance(start, int) and isinstance(end, int) and 0 <= start <= end <= len(text)
        segments.append(SegmentRecord(str(row.get("id", "")),
            text[start:end] if valid_span else str(row.get("text", "")),
            start if valid_span else None, end if valid_span else None,
            dict(row.get("source_origin") or {})))
    return tuple(segments)


@dataclass(frozen=True)
class RepresentationRecord:
    representation_id: str
    file_id: str
    text: str
    segments: tuple[SegmentRecord, ...] = ()
    kind: str = "canonical_extracted_text"
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    file_id: str
    kind: str
    media_type: str
    title: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ArtifactContent:
    artifact: ArtifactRecord
    data: bytes


class LibraryReader(Protocol):
    def list_documents(self, scope: ReadScope = ReadScope(), *, limit: int = 100,
                       cursor: str | None = None) -> Page[DocumentRecord]: ...
    def get_document(self, file_id: str) -> DocumentRecord | None: ...
    def get_representation(self, file_id: str, representation_id: str = "preferred") -> RepresentationRecord | None: ...
    def list_artifacts(self, file_id: str, *, limit: int = 100,
                       cursor: str | None = None) -> Page[ArtifactRecord]: ...
    def get_artifact(self, file_id: str, artifact_id: str, *,
                     max_bytes: int | None = 5 * 1024 * 1024) -> ArtifactContent | None: ...


def page_size(limit: int) -> int:
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError("Read page limit must be between 1 and 500")
    return limit


def cursor_encode(context: str, key: list[str]) -> str:
    return base64.urlsafe_b64encode(json.dumps([1, context, key]).encode()).decode().rstrip("=")


def cursor_decode(cursor: str | None, context: str, width: int) -> list[str] | None:
    if cursor is None:
        return None
    try:
        if not cursor or len(cursor) > 16384:
            raise ValueError
        version, saved_context, key = json.loads(base64.b64decode(
            cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True))
        if version != 1 or saved_context != context or not isinstance(key, list) or len(key) != width:
            raise ValueError
        if not all(isinstance(item, str) for item in key):
            raise ValueError
        return key
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ValueError("Invalid cursor for this read") from exc


def scope_context(scope: ReadScope) -> str:
    return json.dumps(["documents", scope.kind, scope.identifier])


def folder_contains(path: str, folder: str) -> bool:
    prefix = folder.strip("/")
    return not prefix or prefix == "." or path.startswith(prefix + "/")
