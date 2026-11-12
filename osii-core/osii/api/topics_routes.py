from osii.processor_sdk import DocumentMetadata
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator

from osii.domain.services.topics import TopicIndexUnavailable
from osii.domain.services.topic_cache import related_documents, topic_map

router = APIRouter(prefix="/api/topics", tags=["topics"])


class TopicScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope_type: Literal["root", "folder", "collection", "object"] = "root"
    folder_id: str | None = None
    collection_id: str | None = None
    file_id: str | None = None

    @model_validator(mode="after")
    def require_identifier(self):
        key = {"folder": "folder_id", "collection": "collection_id", "object": "file_id"}.get(self.scope_type)
        if key and not (getattr(self, key) or "").strip():
            raise ValueError(f"{key} is required")
        return self


class MapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: TopicScope = Field(default_factory=TopicScope)
    limit: int | None = Field(default=None, ge=1)


class RelatedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: TopicScope = Field(default_factory=TopicScope)
    file_id: str = Field(min_length=1)
    limit: int = Field(default=12, ge=1, le=50)


class IndexResponse(BaseModel):
    id: str
    provider: str
    model: str
    dimensions: int
    semantic: bool
    created_utc: str | None


class DocumentResponse(BaseModel):
    file_id: str
    filename: str
    source_relpath: str
    chunk_count: int
    media_type: str | None = None
    document_title: str | None = None
    title_method: str | None = None
    document_metadata: DocumentMetadata | None = None


class PointResponse(DocumentResponse):
    x: FiniteFloat
    y: FiniteFloat


class MapResponse(BaseModel):
    index: IndexResponse
    scope_count: int
    indexed_count: int
    stale_count: int
    unindexed_count: int
    shown_count: int
    projection: Literal["pca"]
    explained_variance: FiniteFloat
    points: list[PointResponse]


class NeighborResponse(DocumentResponse):
    similarity: FiniteFloat


class RelatedResponse(BaseModel):
    index: IndexResponse
    document: DocumentResponse
    results: list[NeighborResponse]


@router.post("/map", response_model=MapResponse)
def map_documents(request: Request, payload: MapRequest):
    try:
        return topic_map(request.app.state.osii_root, payload.scope.model_dump(exclude_none=True), payload.limit)
    except TopicIndexUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/related", response_model=RelatedResponse)
def related(request: Request, payload: RelatedRequest):
    try:
        return related_documents(request.app.state.osii_root, payload.scope.model_dump(exclude_none=True), payload.file_id, payload.limit)
    except TopicIndexUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
