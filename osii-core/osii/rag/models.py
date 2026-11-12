from typing import Any

from pydantic import BaseModel, Field, field_validator
from typing import Literal


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
    top_k: int | None = Field(default=None, ge=1, le=50)
    profile_id: str = Field(default="default", max_length=100)


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
    representation: str | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[CitationModel]
    provider: str
    fallback_used: bool = False
    retrieval_mode: str
    profile_id: str = "default"
    model: str | None = None
    experiment: dict[str, Any] | None = None


class CompareRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    scope: ScopeModel
    history: list[ChatTurn] = Field(default_factory=list, max_length=12)
    profile_ids: list[str] = Field(default_factory=lambda: ["lexical-v1", "hybrid-v1"], min_length=2, max_length=3)

    @field_validator("profile_ids")
    @classmethod
    def unique_profiles(cls, values):
        if len(set(values)) != len(values):
            raise ValueError("Choose distinct profiles")
        return values


class ComparedRun(BaseModel):
    profile_id: str
    status: Literal["ok", "error"]
    response: ChatResponse | None = None
    error: str | None = None


class ComparisonResponse(BaseModel):
    query: str
    scope: ScopeModel
    corpus_check: str
    model: str
    runs: list[ComparedRun]
