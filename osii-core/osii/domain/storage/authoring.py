"""Core authoring and collection contracts, independent of transport and storage.

These edit derived products, not original evidence. Hosted authorization belongs
to the composition; an actor ID is attribution, never an authorization grant.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
import hashlib
import json
from typing import Any, Literal, Protocol

from osii.domain.read.contracts import ReadScope


class AuthoringConflict(FileExistsError):
    """The active revision or collection version changed since it was read."""


@dataclass(frozen=True)
class ProductRef:
    scope: ReadScope
    filename: str
    family: Literal["synthesis", "enrichment"] = "enrichment"

    def __post_init__(self):
        if self.family not in {"synthesis", "enrichment"}:
            raise ValueError("Unsupported product family")
        path = PurePosixPath(self.filename)
        if (not self.filename or len(self.filename) > 4096 or path.is_absolute() or
            any(part.startswith(".") for part in path.parts) or any(c in self.filename for c in "\\\0")):
            raise ValueError("Invalid product reference")

    def legacy_scope(self) -> dict:
        key = {"object": "file_id", "folder": "folder_id", "collection": "collection_id"}.get(self.scope.kind)
        return {"scope_type": self.scope.kind, **({key: self.scope.identifier} if key else {})}

    @classmethod
    def from_scope(cls, scope: dict, filename: str, family: str = "enrichment") -> ProductRef:
        kind = scope.get("scope_type") or scope.get("type")
        key = {"object": "file_id", "folder": "folder_id", "collection": "collection_id"}.get(kind)
        return cls(ReadScope(kind, scope.get(key, "") if key else "root"), filename, family)


@dataclass(frozen=True)
class ProductRevision:
    revision_id: str
    parent_id: str | None
    origin: str
    data: dict[str, Any]
    provenance: dict[str, Any]
    created_at: str | None = None
    actor_id: str | None = None
    grounding_needs_review: bool = False


@dataclass(frozen=True)
class ProductHistory:
    product: ProductRef
    active_revision: str | None
    revisions: tuple[ProductRevision, ...]

    @property
    def active(self) -> ProductRevision | None:
        return next((row for row in self.revisions if row.revision_id == self.active_revision), None)


def product_history(ref: ProductRef, current: str | None, rows: list[dict]) -> ProductHistory:
    return ProductHistory(ref, current, tuple(ProductRevision(row["id"], row.get("parent"),
        row["origin"], row["data"], row.get("provenance") or {}, row.get("created_at"),
        row.get("actor_id"), row["origin"] == "human") for row in rows))


def validate_product_edit(previous: dict, data: dict, *, max_characters: int = 4_000_000) -> dict:
    """Preserve the product format and reject invalid typed artifacts before writing."""
    from pydantic import TypeAdapter
    from osii.processor_sdk.models import StandardArtifactData
    if not isinstance(data, dict) or len(json.dumps(data, allow_nan=False)) > max_characters:
        raise ValueError(f"Product must be a JSON object of at most {max_characters:,} characters")
    kind = previous.get("artifact_type")
    if data.get("artifact_type") != kind:
        raise ValueError("Preserve the product format when editing")
    if kind == "text":
        if not isinstance(data.get("text"), str):
            raise ValueError("Text products require text content")
    elif kind == "document_metadata":
        from osii.processor_sdk.document_metadata import DocumentMetadata
        record = DocumentMetadata.model_validate(data.get("document_metadata"))
        data = {**data, "document_metadata": record.model_copy(update={"method": "human", "model": None}).model_dump(mode="json")}
    elif kind in {"wiki_markdown", "table", "entity_list", "knowledge_graph"}:
        # Validate without expanding optional citation fields or rewriting the
        # caller's existing provenance/geometry representation.
        TypeAdapter(StandardArtifactData).validate_python(data)
    return data


class ProductAuthoring(Protocol):
    def history(self, product: ProductRef) -> ProductHistory: ...
    def save(self, product: ProductRef, data: dict, *, expected_revision: str | None,
             activate: bool = False, actor_id: str | None = None) -> ProductRevision: ...
    def activate(self, product: ProductRef, revision_id: str, *, expected_revision: str | None,
                 actor_id: str | None = None) -> ProductRevision: ...


def validate_identifier(value: str) -> None:
    if not isinstance(value, str) or not value or len(value) > 4096 or value in {".", ".."} or any(c in value for c in "/\\\0"):
        raise ValueError("Invalid logical identifier")


def normalized_members(values) -> tuple[str, ...]:
    if isinstance(values, str):
        raise ValueError("Members must be document identifiers, not a string")
    result = []
    for value in values:
        validate_identifier(value)
        result.append(value)
    return tuple(sorted(set(result)))


def collection_version(record: dict, members) -> str:
    # Opaque optimistic-concurrency token, including backend-specific metadata.
    payload = {"record": record, "members": normalized_members(members)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class CollectionRecord:
    collection_id: str
    name: str
    description: str | None
    member_ids: tuple[str, ...]
    version: str
    metadata: dict[str, Any] = field(default_factory=dict)


def collection_record(record: dict, members) -> CollectionRecord:
    ids = normalized_members(members)
    return CollectionRecord(record["id"], record["name"], record.get("description"), ids,
        collection_version(record, ids), {k: v for k, v in record.items() if k not in {"id", "name", "description", "members"}})


class CollectionStore(Protocol):
    def list(self) -> tuple[CollectionRecord, ...]: ...
    def get(self, collection_id: str) -> CollectionRecord | None: ...
    def create(self, name: str, *, description: str | None = None,
               collection_id: str | None = None) -> CollectionRecord: ...
    def update(self, collection_id: str, *, expected_version: str, name: str | None = None,
               description: str | None = None) -> CollectionRecord: ...
    def replace_members(self, collection_id: str, member_ids, *, expected_version: str) -> CollectionRecord: ...
