"""Storage-, transport-, and framework-independent contracts for RAG experiments."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal, Mapping, Protocol, Sequence


class StrategyError(ValueError):
    """An experiment violated its input, evidence, or generation contract."""


@dataclass(frozen=True)
class Scope:
    kind: Literal["root", "folder", "collection", "object"] = "root"
    identifier: str = ""

    def __post_init__(self):
        if self.kind not in {"root", "folder", "collection", "object"}:
            raise StrategyError("Unsupported scope")
        if self.kind != "root" and not self.identifier.strip():
            raise StrategyError("A non-root scope requires an identifier")

    def payload(self) -> dict[str, str]:
        result = {"scope_type": self.kind}
        key = {"folder": "folder_id", "collection": "collection_id", "object": "file_id"}.get(self.kind)
        if key:
            result[key] = self.identifier
        return result


@dataclass(frozen=True)
class Evidence:
    id: str
    file_id: str
    text: str
    source_relpath: str = ""
    representation: str = "preferred"
    char_start: int | None = None
    char_end: int | None = None
    source_origin: Mapping = field(default_factory=dict)
    corpus_revision: str | None = None

    def __post_init__(self):
        if not self.id or not self.file_id or not self.text.strip():
            raise StrategyError("Evidence requires a stable ID, file ID, and nonempty text")
        if (self.char_start is None) != (self.char_end is None):
            raise StrategyError("Evidence spans require both offsets")
        if self.char_start is not None and not 0 <= self.char_start <= self.char_end:
            raise StrategyError("Invalid evidence character span")


@dataclass(frozen=True)
class Limits:
    max_retrievals: int = 3
    max_model_calls: int = 3
    top_k: int = 6
    max_evidence: int = 18
    max_context_chars: int = 24000
    max_output_tokens: int = 900
    deadline_seconds: float = 90

    def __post_init__(self):
        for name, lower, upper in (("max_retrievals", 1, 8), ("max_model_calls", 1, 8),
                ("top_k", 1, 50), ("max_evidence", 1, 50), ("max_context_chars", 100, 64000),
                ("max_output_tokens", 32, 4096)):
            if not isinstance(getattr(self, name), int) or not lower <= getattr(self, name) <= upper:
                raise StrategyError(f"{name} must be between {lower} and {upper}")
        if not 0 < self.deadline_seconds <= 600:
            raise StrategyError("deadline_seconds must be positive and at most 600")


@dataclass(frozen=True)
class Question:
    text: str
    scope: Scope = field(default_factory=Scope)
    history: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        if not self.text.strip() or len(self.text) > 4000:
            raise StrategyError("Questions must contain 1–4,000 characters")
        if len(self.history) > 12 or sum(len(text) for _, text in self.history) > 12000:
            raise StrategyError("Conversation history exceeds the experiment limit")
        if any(role not in {"user", "assistant"} for role, _ in self.history):
            raise StrategyError("Unsupported conversation role")


@dataclass(frozen=True)
class Context:
    question: Question
    evidence: tuple[Evidence, ...]
    queries: tuple[str, ...]
    can_retrieve: bool
    max_output_tokens: int


@dataclass(frozen=True)
class Decision:
    action: Literal["retrieve", "answer", "abstain"]
    query: str = ""
    answer: str = ""
    citation_ids: tuple[str, ...] = ()
    model: str = ""
    usage: Mapping = field(default_factory=dict)

    def __post_init__(self):
        if self.action not in {"retrieve", "answer", "abstain"}:
            raise StrategyError("Unsupported decision action")
        if self.action == "retrieve" and (not self.query.strip() or len(self.query) > 4000):
            raise StrategyError("A follow-up query must contain 1–4,000 characters")
        if self.action == "answer" and (not self.answer.strip() or len(self.answer) > 16000):
            raise StrategyError("An answer must contain 1–16,000 characters")


class Retriever(Protocol):
    """An adapter already bound to the caller's authorized scope; no writes."""
    def __call__(self, query: str, *, top_k: int) -> Sequence[Evidence]: ...


Decider = Callable[[Context], Decision]


@dataclass(frozen=True)
class Step:
    query: str
    added_ids: tuple[str, ...]
    action: str
    model: str = ""
    usage: Mapping = field(default_factory=dict)


@dataclass(frozen=True)
class Result:
    answer: str
    citations: tuple[Evidence, ...]
    evidence: tuple[Evidence, ...]
    steps: tuple[Step, ...]
    stop_reason: str
    retrieval_calls: int
    model_calls: int
    elapsed_seconds: float
    strategy: str
