"""Portable execution facts for RAG stages; no store, HTTP, or framework imports."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import time
import uuid


@dataclass
class TraceStage:
    id: str
    parent_id: str | None
    kind: str
    label: str
    started_seconds: float
    duration_seconds: float = 0
    status: str = "running"
    inputs: dict = field(default_factory=dict)
    outputs: dict = field(default_factory=dict)
    items: list[dict] = field(default_factory=list)
    excluded: list[dict] = field(default_factory=list)


class AgentTrace:
    """One request's bounded, explicit stage records, safe to export as JSON.

    Callers supply public settings only: never pass provider objects or secrets.
    Execution records and later quality annotations are deliberately separate.
    """
    def __init__(self, profile_id: str, *, item_limit: int = 200):
        self.id = str(uuid.uuid4())
        self.profile_id = profile_id
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.started = time.perf_counter()
        self.stages: list[TraceStage] = []
        self.parents: list[str] = []
        self.item_limit = item_limit

    @staticmethod
    def evidence(row: dict) -> dict:
        keys = ("id", "chunk_id", "file_id", "filename", "source_relpath", "score", "match_type",
                "representation", "char_start", "char_end", "source_origin", "rank", "reason")
        value = {key: deepcopy(row[key]) for key in keys if key in row}
        if isinstance(row.get("text"), str):
            value.update(text=row["text"][:4000], text_characters=len(row["text"]), text_truncated=len(row["text"]) > 4000)
        return value

    @contextmanager
    def span(self, kind: str, label: str, **inputs):
        stage = TraceStage(str(len(self.stages) + 1), self.parents[-1] if self.parents else None,
                           kind, label, time.perf_counter() - self.started, inputs=deepcopy(inputs))
        self.stages.append(stage)
        self.parents.append(stage.id)
        start = time.perf_counter()
        try:
            yield stage
            stage.status = "completed"
        except Exception as exc:
            stage.status = "error"
            stage.outputs["error_type"] = type(exc).__name__
            raise
        finally:
            stage.duration_seconds = time.perf_counter() - start
            self.parents.pop()
            for name in ("items", "excluded"):
                rows = getattr(stage, name)
                stage.outputs[name + "_recorded"] = min(len(rows), self.item_limit)
                stage.outputs[name + "_omitted"] = max(0, len(rows) - self.item_limit)
                setattr(stage, name, [self.evidence(row) for row in rows[:self.item_limit]])

    def observe(self, kind: str, *, items: list[dict], input_count: int,
                duration_seconds: float, excluded: list[dict] | None = None, **details):
        """Adapter for retrieval operations that already measured their work."""
        labels = {"bm25": "BM25 passage ranking", "ocr_tolerant_search": "OCR-tolerant term search",
                  "semantic_search": "Semantic passage ranking", "rank_fusion": "Reciprocal-rank fusion",
                  "passage_selection": "Select non-overlapping passages"}
        with self.span(kind, labels.get(kind, kind.replace("_", " ").title()), input_count=input_count) as stage:
            stage.items = items
            stage.excluded = excluded or []
            stage.outputs.update(output_count=len(items), **details)
        stage.duration_seconds = duration_seconds
        stage.started_seconds = max(0, stage.started_seconds - duration_seconds)

    def export(self, *, detailed: bool = True, **metadata) -> dict:
        stages = [asdict(stage) for stage in self.stages]
        if not detailed:
            for stage in stages:
                stage["items"], stage["excluded"] = [], []
                # Keep execution counts/status visible; detailed payloads are admin-only.
                stage["inputs"] = {k: v for k, v in stage["inputs"].items() if k.endswith("count")}
                stage["outputs"] = {k: v for k, v in stage["outputs"].items()
                                    if k.endswith(("count", "recorded", "omitted")) or k in {"error_type", "limit_reached"}}
        return {"schema_version": "osii.agent-trace.v1", "id": self.id, "profile_id": self.profile_id,
                "created_at": self.created_at, "elapsed_seconds": time.perf_counter() - self.started,
                "capture_level": "detailed" if detailed else "summary", "stages": stages,
                "persistence": "response-only; download JSON to retain this run", **metadata}
