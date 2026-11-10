"""Validated Core processing commits; independent of storage and transport.

These are Core contracts, not another processor protocol. Processors still return
the existing SDK responses. One command commits one document's completed step.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import base64
import hashlib
import json
import math
from typing import Any, Protocol
import uuid

from pydantic import BaseModel

from osii.domain.read.contracts import LibraryReader
from osii.processor_sdk import (EmbeddingRequest, EmbeddingResponse, EnrichmentRequest,
    EnrichmentResponse, ExtractionRequest, ExtractionResponse, ProcessorDescriptor,
    ProvenanceRef, SynthesisRequest, SynthesisResponse)

Request = ExtractionRequest | SynthesisRequest | EnrichmentRequest | EmbeddingRequest
Response = ExtractionResponse | SynthesisResponse | EnrichmentResponse | EmbeddingResponse


class CommitConflict(ValueError):
    """A stale input or reused operation ID cannot overwrite a newer result."""


def text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        allow_nan=False, separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class InputRevision:
    file_id: str
    representation_id: str
    text_sha256: str

    @classmethod
    def capture(cls, reader: LibraryReader, file_id: str) -> InputRevision:
        record = reader.get_representation(file_id)
        if record is None:
            raise CommitConflict("No preferred input text is available")
        return cls(file_id, record.representation_id, text_digest(record.text))

    def verify(self, reader: LibraryReader) -> None:
        if self != self.capture(reader, self.file_id):
            raise CommitConflict("Preferred text changed; stage a new processing step")


@dataclass(frozen=True)
class SourceRecord:
    file_id: str
    source_relpath: str
    filename: str
    media_type: str
    sha256: str
    size_bytes: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class JobCheckpoint:
    job_id: str
    worker_id: str
    index: int | None = None
    item: dict[str, Any] | None = None


@dataclass(frozen=True)
class ProcessingCommit:
    operation_id: str
    file_id: str
    request: Request
    response: Response
    expected_processor: ProcessorDescriptor
    input_revision: InputRevision | None = None
    source: SourceRecord | None = None
    make_primary: bool = True
    # Preserve existing representation layouts when adapting a legacy workflow.
    text_separator: str = "\n"
    chunks: tuple[dict[str, Any], ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def kind(self) -> str:
        return {ExtractionResponse: "extraction", SynthesisResponse: "synthesis",
                EnrichmentResponse: "enrichment", EmbeddingResponse: "embedding"}[type(self.response)]

    @property
    def commit_id(self) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(["osii-commit-v1", self.file_id, self.operation_id])))

    def fingerprint(self) -> str:
        from dataclasses import asdict
        excluded = {"model_context": True, "request_id": True}
        if isinstance(self.request, ExtractionRequest):
            excluded["document"] = {"content_base64"}
        request = self.request.model_dump(mode="json", exclude=excluded)
        response = self.response.model_dump(mode="json", exclude={"request_id"})
        return digest({"request": request, "response": response, "processor": self.expected_processor.model_dump(mode="json"),
            "input": asdict(self.input_revision) if self.input_revision else None,
            "source": asdict(self.source) if self.source else None, "make_primary": self.make_primary,
            "separator": self.text_separator, "chunks": self.chunks, "provenance": self.provenance})

    def validate(self) -> None:
        if not self.operation_id or len(self.operation_id) > 1000:
            raise ValueError("A bounded operation_id is required")
        if not self.file_id or self.file_id in {".", ".."} or any(c in self.file_id for c in "/\\\0"):
            raise ValueError("Invalid document identifier")
        response = type(self.response).model_validate(self.response.model_dump(mode="json"))
        expected = self.expected_processor
        if (response.request_id != self.request.request_id or
            (response.processor.name, response.processor.version, response.processor.kind) !=
            (expected.name, expected.version, expected.kind)):
            raise ValueError("Processor response does not match the requested operation")
        pairs = {ExtractionRequest: ExtractionResponse, SynthesisRequest: SynthesisResponse,
                 EnrichmentRequest: EnrichmentResponse, EmbeddingRequest: EmbeddingResponse}
        kinds = {ExtractionResponse: "extractor", SynthesisResponse: "synthesizer",
                 EnrichmentResponse: "enricher", EmbeddingResponse: "embedder"}
        if pairs.get(type(self.request)) is not type(response) or expected.kind.value != kinds[type(response)]:
            raise ValueError("Request, response, and processor kinds must agree")
        if isinstance(response, ExtractionResponse):
            if not self.source or self.source.file_id != self.file_id or self.request.document.file_id != self.file_id:
                raise ValueError("Extraction needs explicit matching source identity")
            if not response.segments:
                raise ValueError("Extraction returned no text segments")
            if len({item.id for item in response.artifacts}) != len(response.artifacts):
                raise ValueError("Extraction artifact IDs must be unique")
            for artifact in response.artifacts:
                if artifact.data_base64 is not None:
                    base64.b64decode(artifact.data_base64, validate=True)
            if self.request.document.content_base64 is not None:
                raw = base64.b64decode(self.request.document.content_base64, validate=True)
                if hashlib.sha256(raw).hexdigest() != self.source.sha256 or len(raw) != self.source.size_bytes:
                    raise CommitConflict("Source bytes do not match the supplied source identity")
        else:
            if self.input_revision is None or self.input_revision.file_id != self.file_id:
                raise ValueError("Derived output requires its explicit input revision")
        if isinstance(self.request, (SynthesisRequest, EnrichmentRequest)):
            scope = self.request.scope
            if scope.scope_type != "object" or scope.scope_id != self.file_id or {doc.file_id for doc in scope.documents} != {self.file_id}:
                raise ValueError("This commit boundary accepts one explicit document scope")
            length = len(scope.documents[0].text or "")
            def check(value):
                if isinstance(value, ProvenanceRef):
                    if value.file_id not in {None, self.file_id}:
                        raise ValueError("Citation escapes the committed scope")
                    if value.char_start is not None and value.char_end is not None and not 0 <= value.char_start <= value.char_end <= length:
                        raise ValueError("Citation span is outside the supplied text")
                elif isinstance(value, BaseModel):
                    for name in type(value).model_fields:
                        check(getattr(value, name))
                elif isinstance(value, (list, tuple)):
                    for child in value:
                        check(child)
            check(response)
        if isinstance(response, EnrichmentResponse):
            for item in response.artifacts:
                if any(char in item.kind + item.id for char in "/\\\0") or item.kind.startswith("."):
                    raise ValueError("Unsafe product name")
        if isinstance(response, EmbeddingResponse):
            if self.request.config.get("model") not in {None, response.model}:
                raise ValueError("Embedding model does not match the requested vector space")
            if [v.id for v in response.vectors] != [item.id for item in self.request.inputs]:
                raise ValueError("Embedding outputs must match input IDs in order")
            for item in response.vectors:
                if not all(math.isfinite(value) for value in item.vector):
                    raise ValueError("Embedding vectors must be finite")
                if response.normalized and not math.isclose(sum(value * value for value in item.vector), 1, abs_tol=0.002):
                    raise ValueError("Embedding normalization metadata is incorrect")
            if self.chunks and [row["chunk_id"] for row in self.chunks] != [item.id for item in self.request.inputs]:
                raise ValueError("Embedding chunks must match the explicit request")
        if isinstance(response, ExtractionResponse) and self.chunks:
            text, _ = extraction_material(self)
            ids = [row["chunk_id"] for row in self.chunks]
            if len(ids) != len(set(ids)):
                raise ValueError("Chunk IDs must be unique")
            for row in self.chunks:
                if (row.get("file_id", self.file_id) != self.file_id or
                    not 0 <= row["char_start"] <= row["char_end"] <= len(text) or
                    row["text"] != text[row["char_start"]:row["char_end"]]):
                    raise ValueError("Chunk does not match the committed extraction")
        self.fingerprint()  # Reject non-JSON/NaN metadata before any writes.


def extraction_material(command: ProcessingCommit) -> tuple[str, list[dict]]:
    parts, records, position = [], [], 0
    for segment in command.response.segments:
        if parts:
            parts.append(command.text_separator)
            position += len(command.text_separator)
        start = position
        parts.append(segment.text)
        position += len(segment.text)
        records.append({"id": segment.id, "char_start": start, "char_end": position,
                        "source_origin": segment.source_origin})
    return "".join(parts), records


def embedding_identity(response: EmbeddingResponse) -> dict:
    return {"provider": response.metadata.get("provider_id") or response.processor.name, "model": response.model,
        "dimensions": response.vectors[0].dimensions if response.vectors else 0,
        "normalized": response.normalized,
        **{key: response.metadata[key] for key in ("model_digest", "endpoint_type", "chunking") if key in response.metadata}}


@dataclass(frozen=True)
class CommitReceipt:
    commit_id: str
    file_id: str
    kind: str
    result: dict[str, Any]
    replayed: bool = False


class ProcessingCommitter(Protocol):
    def commit(self, command: ProcessingCommit, *, checkpoint: JobCheckpoint | None = None) -> CommitReceipt: ...
