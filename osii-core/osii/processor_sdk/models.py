from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel as PydanticBaseModel, ConfigDict, Field, model_validator

API_VERSION = "v1"


class BaseModel(PydanticBaseModel):
    model_config = ConfigDict(extra="forbid")


class ProcessorKind(StrEnum):
    EXTRACTOR = "extractor"
    SYNTHESIZER = "synthesizer"
    EMBEDDER = "embedder"
    ENRICHER = "enricher"


class Capability(BaseModel):
    media_types: list[str] = Field(default_factory=list)
    file_extensions: list[str] = Field(default_factory=list)
    scope_types: list[Literal["object", "folder", "collection", "root"]] = Field(default_factory=list)
    output_kinds: list[str] = Field(default_factory=list)


class ProcessorDescriptor(BaseModel):
    api_version: Literal["v1"] = API_VERSION
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    version: str
    display_name: str
    description: str
    kind: ProcessorKind
    capabilities: Capability = Field(default_factory=Capability)
    config_schema: dict[str, Any] = Field(default_factory=dict)


class TextSegment(BaseModel):
    id: str
    text: str
    segment_type: str = "text"
    source_origin: dict[str, Any] = Field(default_factory=dict)
    related_ids: list[str] = Field(default_factory=list)


class ProvenanceRef(BaseModel):
    file_id: str | None = None
    segment_id: str | None = None
    page: int | None = Field(default=None, ge=1)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    source_origin: dict[str, Any] = Field(default_factory=dict)


class TableColumn(BaseModel):
    key: str
    label: str
    data_type: Literal["string", "number", "integer", "boolean", "date", "datetime", "json"] = "string"
    unit: str | None = None
    description: str | None = None


class TableArtifactData(BaseModel):
    artifact_type: Literal["table"] = "table"
    title: str
    description: str | None = None
    columns: list[TableColumn]
    rows: list[dict[str, Any]]
    row_provenance: list[list[ProvenanceRef]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_table(self) -> "TableArtifactData":
        keys = [column.key for column in self.columns]
        if len(keys) != len(set(keys)):
            raise ValueError("table column keys must be unique")
        if self.row_provenance and len(self.row_provenance) != len(self.rows):
            raise ValueError("row_provenance must be empty or match rows")
        return self


class KnowledgeGraphNode(BaseModel):
    id: str
    label: str
    entity_type: str
    properties: dict[str, Any] = Field(default_factory=dict)
    provenance: list[ProvenanceRef] = Field(default_factory=list)


class KnowledgeGraphEdge(BaseModel):
    id: str
    source: str
    target: str
    relation: str
    properties: dict[str, Any] = Field(default_factory=dict)
    provenance: list[ProvenanceRef] = Field(default_factory=list)


class KnowledgeGraphArtifactData(BaseModel):
    artifact_type: Literal["knowledge_graph"] = "knowledge_graph"
    title: str
    description: str | None = None
    nodes: list[KnowledgeGraphNode]
    edges: list[KnowledgeGraphEdge]

    @model_validator(mode="after")
    def validate_graph(self) -> "KnowledgeGraphArtifactData":
        node_ids = [node.id for node in self.nodes]
        edge_ids = [edge.id for edge in self.edges]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("knowledge graph node IDs must be unique")
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("knowledge graph edge IDs must be unique")
        known = set(node_ids)
        if any(edge.source not in known or edge.target not in known for edge in self.edges):
            raise ValueError("knowledge graph edges must reference existing nodes")
        return self


class Entity(BaseModel):
    id: str
    name: str
    entity_type: str
    aliases: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    mentions: list[ProvenanceRef] = Field(default_factory=list)


class EntityListArtifactData(BaseModel):
    artifact_type: Literal["entity_list"] = "entity_list"
    title: str
    description: str | None = None
    entities: list[Entity]

    @model_validator(mode="after")
    def unique_entity_ids(self) -> "EntityListArtifactData":
        ids = [entity.id for entity in self.entities]
        if len(ids) != len(set(ids)):
            raise ValueError("entity IDs must be unique")
        return self


class WikiMarkdownArtifactData(BaseModel):
    artifact_type: Literal["wiki_markdown"] = "wiki_markdown"
    title: str
    markdown: str
    citations: list[ProvenanceRef] = Field(default_factory=list)


StandardArtifactData = Annotated[
    TableArtifactData
    | KnowledgeGraphArtifactData
    | EntityListArtifactData
    | WikiMarkdownArtifactData,
    Field(discriminator="artifact_type"),
]


class Artifact(BaseModel):
    id: str
    kind: str
    media_type: str
    data_base64: str | None = None
    text: str | None = None
    json_data: Any | None = None
    source_origin: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    standard_data: StandardArtifactData | None = None

    @model_validator(mode="after")
    def exactly_one_payload(self) -> "Artifact":
        values = (self.data_base64, self.text, self.json_data, self.standard_data)
        if sum(value is not None for value in values) != 1:
            raise ValueError("artifact must contain exactly one payload")
        return self


class DocumentInput(BaseModel):
    file_id: str | None = None
    filename: str
    media_type: str = "application/octet-stream"
    content_base64: str | None = None
    text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    segments: list[TextSegment] = Field(default_factory=list)


class ScopeInput(BaseModel):
    scope_type: Literal["object", "folder", "collection", "root"]
    scope_id: str
    documents: list[DocumentInput] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExtractionRequest(BaseModel):
    api_version: Literal["v1"] = API_VERSION
    request_id: str
    document: DocumentInput
    expert_context: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class ExtractionResponse(BaseModel):
    api_version: Literal["v1"] = API_VERSION
    request_id: str
    processor: ProcessorDescriptor
    segments: list[TextSegment]
    artifacts: list[Artifact] = Field(default_factory=list)
    document_metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_segment_ids(self) -> "ExtractionResponse":
        ids = [segment.id for segment in self.segments]
        if len(ids) != len(set(ids)):
            raise ValueError("extraction segment IDs must be unique")
        return self


class SynthesisRequest(BaseModel):
    api_version: Literal["v1"] = API_VERSION
    request_id: str
    scope: ScopeInput
    expert_context: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class SynthesisResponse(BaseModel):
    api_version: Literal["v1"] = API_VERSION
    request_id: str
    processor: ProcessorDescriptor
    markdown: str
    citations: list[ProvenanceRef] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class EmbeddingInput(BaseModel):
    id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class EmbeddingRequest(BaseModel):
    api_version: Literal["v1"] = API_VERSION
    request_id: str
    inputs: list[EmbeddingInput] = Field(min_length=1)
    config: dict[str, Any] = Field(default_factory=dict)


class EmbeddingVector(BaseModel):
    id: str
    vector: list[float]
    dimensions: int = Field(gt=0)

    @model_validator(mode="after")
    def dimensions_match(self) -> "EmbeddingVector":
        if len(self.vector) != self.dimensions:
            raise ValueError("dimensions must equal vector length")
        return self


class EmbeddingResponse(BaseModel):
    api_version: Literal["v1"] = API_VERSION
    request_id: str
    processor: ProcessorDescriptor
    model: str
    vectors: list[EmbeddingVector]
    normalized: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def consistent_vectors(self) -> "EmbeddingResponse":
        ids = [item.id for item in self.vectors]
        dimensions = {item.dimensions for item in self.vectors}
        if len(ids) != len(set(ids)):
            raise ValueError("embedding vector IDs must be unique")
        if len(dimensions) > 1:
            raise ValueError("all vectors must use the same dimensions")
        return self


class EnrichmentRequest(BaseModel):
    api_version: Literal["v1"] = API_VERSION
    request_id: str
    scope: ScopeInput
    expert_context: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class EnrichmentResponse(BaseModel):
    api_version: Literal["v1"] = API_VERSION
    request_id: str
    processor: ProcessorDescriptor
    artifacts: list[Artifact] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_artifact_ids(self) -> "EnrichmentResponse":
        ids = [artifact.id for artifact in self.artifacts]
        if len(ids) != len(set(ids)):
            raise ValueError("enrichment artifact IDs must be unique")
        if any(artifact.standard_data is None for artifact in self.artifacts):
            raise ValueError("enrichment artifacts must use a standard_data format")
        return self
