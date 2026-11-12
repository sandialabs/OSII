"""Shared, typed suggestions inferred during synthesis, never canonical facts."""

from __future__ import annotations

from typing import Literal
from pydantic import Field, field_validator
from .models import BaseModel


class MetadataSuggestion(BaseModel):
    value: str | None = Field(default=None, max_length=240)
    qualifier: str | None = Field(default=None, max_length=1000)
    evidence: str | None = Field(default=None, max_length=500)

    @field_validator("value", "qualifier", "evidence", mode="before")
    @classmethod
    def blank_is_unknown(cls, value):
        return value.strip() or None if isinstance(value, str) else value


class DocumentMetadata(BaseModel):
    schema_version: Literal[1] = 1
    method: str = "text_llm"
    model: str | None = None
    title: MetadataSuggestion
    author: MetadataSuggestion
    date: MetadataSuggestion
    descriptive_title: MetadataSuggestion = Field(default_factory=MetadataSuggestion)
    agency: MetadataSuggestion = Field(default_factory=MetadataSuggestion)
    document_type: MetadataSuggestion = Field(default_factory=MetadataSuggestion)
