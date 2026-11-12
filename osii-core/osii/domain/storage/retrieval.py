"""Bounded retrieval boundary shared by the two existing search compositions.

Ranking and scope authorization remain with the supplied native search function.
Snippets are explicitly display excerpts, not fabricated full source passages.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import math
from typing import Callable, Literal, Protocol

from osii.domain.read.contracts import ReadScope


@dataclass(frozen=True)
class RetrievalRequest:
    query: str
    scope: ReadScope = field(default_factory=ReadScope)
    mode: Literal["lexical", "semantic", "hybrid"] = "hybrid"
    top_k: int = 10
    max_text_chars: int = 64000
    group_by: Literal["file"] | None = None

    def __post_init__(self):
        if not self.query.strip() or len(self.query) > 4000:
            raise ValueError("Search queries must contain 1–4,000 characters")
        if self.mode not in {"lexical", "semantic", "hybrid"}:
            raise ValueError("Unsupported retrieval mode")
        if type(self.top_k) is not int or not 1 <= self.top_k <= 50:
            raise ValueError("top_k must be between 1 and 50")
        if type(self.max_text_chars) is not int or not 1 <= self.max_text_chars <= 128000:
            raise ValueError("Retrieval text budget must be between 1 and 128,000 characters")
        if self.group_by not in {None, "file"}:
            raise ValueError("Unsupported retrieval grouping")

    def scope_payload(self) -> dict:
        key = {"object": "file_id", "folder": "folder_id", "collection": "collection_id"}.get(self.scope.kind)
        return {"scope_type": self.scope.kind, **({key: self.scope.identifier} if key else {})}


@dataclass(frozen=True)
class RetrievalHit:
    file_id: str
    passage_id: str | None
    source_relpath: str
    representation: str | None
    char_start: int | None
    char_end: int | None
    source_origin: dict
    snippet: str | None
    text: str | None
    score: float | None
    native: dict = field(repr=False)


@dataclass(frozen=True)
class RetrievalResult:
    request: RetrievalRequest
    hits: tuple[RetrievalHit, ...]
    actual_mode: str
    channels: tuple[str, ...]
    corpus_revision: str | None
    limited: bool
    metadata: dict = field(default_factory=dict)

    def legacy_rows(self) -> list[dict]:
        return [deepcopy(hit.native) for hit in self.hits]


class Retriever(Protocol):
    def retrieve(self, request: RetrievalRequest) -> RetrievalResult: ...


class BoundedRetriever:
    """Adapt native search without choosing a model, index, or fallback policy."""
    def __init__(self, search: Callable[[RetrievalRequest], dict]):
        self.search = search

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        response = self.search(request)
        mode = response.get("retrieval_mode_used", request.mode)
        if mode not in {"lexical", "semantic", "hybrid", "empty"}:
            raise ValueError("Search returned an unknown retrieval mode")
        rows = response.get("results", [])
        hits, used, limited = [], 0, len(rows) > request.top_k
        for raw in rows[:request.top_k]:
            row = deepcopy(raw)
            # Vectors are internal ranking state, not a retrieval response.
            row.pop("embedding", None)
            if not isinstance(row.get("file_id"), str) or not row["file_id"]:
                raise ValueError("A retrieval hit requires a document ID")
            if request.scope.kind == "object" and row["file_id"] != request.scope.identifier:
                raise ValueError("Retrieval hit escapes its object scope")
            start, end = row.get("char_start"), row.get("char_end")
            if (start is None) != (end is None) or (start is not None and
                (type(start) is not int or type(end) is not int or not 0 <= start <= end)):
                raise ValueError("Retrieval returned invalid source offsets")
            score = row.get("score")
            if score is not None and (not isinstance(score, (int, float)) or not math.isfinite(score)):
                raise ValueError("Retrieval scores must be finite")
            text, snippet = row.get("text"), row.get("snippet")
            if any(value is not None and not isinstance(value, str) for value in (text, snippet)):
                raise ValueError("Retrieval text must be text")
            cost = len(text or "") + len(snippet or "")
            if used + cost > request.max_text_chars:
                limited = True
                continue  # Do not truncate text and pretend its source spans changed.
            used += cost
            hits.append(RetrievalHit(row["file_id"], row.get("chunk_id") or row.get("segment_id"),
                row.get("source_relpath", ""), row.get("representation") or row.get("source_text_representation"),
                start, end, deepcopy(row.get("source_origin") or {}), snippet, text, score, row))
        revision = response.get("corpus_revision")
        return RetrievalResult(request, tuple(hits), mode, tuple(response.get("channels_used") or ()),
            str(revision) if revision is not None else None, limited,
            {key: deepcopy(value) for key, value in response.items() if key != "results"})
