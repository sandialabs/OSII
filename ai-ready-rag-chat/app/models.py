from pydantic import BaseModel, Field
from typing import Any


class ScopeModel(BaseModel):
    scope_type: str
    folder_id: str | None = None
    collection_id: str | None = None
    file_id: str | None = None


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    query: str = Field(min_length=1)
    scope: ScopeModel
    history: list[ChatTurn] = Field(default_factory=list)
    top_k: int | None = None


class CitationModel(BaseModel):
    file_id: str | None = None
    filename: str | None = None
    source_relpath: str | None = None
    snippet: str | None = None
    chunk_id: str | None = None
    segment_id: str | None = None
    page: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    source_origin: dict[str, Any] | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[CitationModel]
    provider: str
    fallback_used: bool = False
    retrieval_mode: str
