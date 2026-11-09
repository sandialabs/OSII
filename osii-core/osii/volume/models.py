from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Filters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: int | None = None
    path: str = ""
    name: str = ""
    suffix: str = ""
    text_state: Literal["any", "metadata_only", "extracted"] = "any"
    min_bytes: int = Field(0, ge=0)
    max_bytes: int | None = Field(None, ge=0)
    modified_after: int | None = None  # UTC seconds
    modified_before: int | None = None
    metadata_state: Literal["any", "known", "unavailable"] = "any"
    sidecar_state: Literal["any", "processed", "missing"] = "any"

    @model_validator(mode="after")
    def valid_ranges(self):
        if self.max_bytes is not None and self.max_bytes < self.min_bytes:
            raise ValueError("Maximum size must be at least minimum size")
        if self.modified_after is not None and self.modified_before is not None:
            if self.modified_after > self.modified_before:
                raise ValueError("Modification dates are reversed")
        return self


class SelectionRequest(BaseModel):
    filters: Filters = Field(default_factory=Filters)
    sample: bool = False
    seed: str = "osii"
    per_stratum: int = Field(2, ge=1, le=100)
    max_files: int = Field(100, ge=1, le=1_000_000)
    max_bytes: int = Field(1024**3, ge=1)
    allow_partial: bool = False


class ScanOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    include_patterns: list[str] = Field(default_factory=list, max_length=100)
    exclude_patterns: list[str] = Field(default_factory=list, max_length=100)
    show_hidden: bool = False
    max_depth: int | None = Field(None, ge=0, le=256)
    cross_filesystems: bool = False
    readers: int = Field(2, ge=1, le=8)
    isolate: bool = True
    timeout_seconds: int = Field(30, ge=1, le=300)


class ProcessRequest(BaseModel):
    selection_id: int
    stage: Literal["extract", "ocr", "synthesize", "enrich"] = "extract"
    endpoint: str = "http://127.0.0.1:8092"
    config: dict = Field(default_factory=dict)
    max_file_bytes: int = Field(50 * 1024**2, ge=1, le=50 * 1024**2)
    max_seconds: int = Field(3600, ge=1)
    max_output_bytes: int = Field(20 * 1024**2, ge=1024, le=50 * 1024**2)

    @model_validator(mode="after")
    def bounded_endpoint(self):
        from urllib.parse import urlsplit

        parsed = urlsplit(self.endpoint)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError(
                "Use an explicit HTTP(S) processor URL without credentials"
            )
        if parsed.query or parsed.fragment:
            raise ValueError("Processor URL cannot include a query or fragment")
        return self
