"""Storage-independent, lossless input batching for scope processors.

Request limits bound one call, never the selected corpus. Storage adapters own
immutable inputs/checkpoints; processors receive explicit text windows only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator, Protocol, Callable, Any
import hashlib

BATCH_CHARACTERS = 100_000
BATCH_DOCUMENTS = 32
REDUCTION_FAN_IN = 4


@dataclass(frozen=True)
class BatchLimits:
    characters: int = BATCH_CHARACTERS
    documents: int = BATCH_DOCUMENTS

    def __post_init__(self):
        if not 1_000 <= self.characters <= 160_000 or not 1 <= self.documents <= 64:
            raise ValueError(
                "Batch limits must be 1,000–160,000 characters and 1–64 documents"
            )


def text_windows(document: dict, limit: int) -> Iterator[dict]:
    """Retain every character once, preferring natural boundaries near the end."""
    text = document["text"]
    start = 0
    digest = document.get("source_sha256") or hashlib.sha256(text.encode()).hexdigest()
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            # Including the delimiter avoids both loss and duplicate word counts.
            cut = max(
                text.rfind("\n", start + limit // 2, end),
                text.rfind(" ", start + limit // 2, end),
            )
            if cut >= 0:
                end = cut + 1
        yield {
            **document,
            "text": text[start:end],
            "char_start": start,
            "char_end": end,
            "full_chars": len(text),
            "source_sha256": digest,
            "truncated": False,
        }
        start = end


def input_batches(
    documents: Iterable[dict], limits: BatchLimits = BatchLimits()
) -> Iterator[list[dict]]:
    batch: list[dict] = []
    size = 0
    identities: set[str] = set()
    for document in documents:
        if not document["text"].strip():
            continue
        for window in text_windows(document, limits.characters):
            if batch and (
                size + len(window["text"]) > limits.characters
                or len(batch) >= limits.documents
                or window["file_id"] in identities
            ):
                yield batch
                batch = []
                size = 0
                identities = set()
            batch.append(window)
            size += len(window["text"])
            identities.add(window["file_id"])
    if batch:
        yield batch


def coverage(documents: list[dict]) -> list[dict]:
    return [
        {key: value for key, value in row.items() if key not in {"text", "native_text"}}
        for row in documents
    ]


def request_scope(scope: dict, documents: list[dict], *, phase="map", batch_id=0):
    from osii.processor_sdk import ScopeInput, DocumentInput

    identity = (
        scope.get("file_id")
        or scope.get("folder_id")
        or scope.get("collection_id")
        or "root"
    )
    return ScopeInput(
        scope_type=scope["scope_type"],
        scope_id=identity,
        documents=[
            DocumentInput(
                file_id=row["file_id"],
                filename=row.get("filename") or row["file_id"],
                media_type=row.get("media_type") or "text/plain",
                text=row["text"],
                metadata={
                    "source_char_start": row.get("char_start", 0),
                    "source_char_end": row.get("char_end", len(row["text"])),
                    "full_characters": row.get("full_chars", len(row["text"])),
                    "extraction_id": row.get("extraction_id"),
                    "source_relpath": row.get("source_relpath"),
                },
            )
            for row in documents
        ],
        metadata={
            "scope_batch": {
                "phase": phase,
                "id": batch_id,
                "inputs_are_derived": phase == "reduce",
            }
        },
    )


def normalize_result(response, documents: list[dict], *, derived=False) -> dict:
    """Validate window citations before translating them to original offsets."""
    body = (
        response.model_dump(mode="json")
        if hasattr(response, "model_dump")
        else response
    )
    import json

    if len(json.dumps(body, ensure_ascii=False).encode("utf-8")) > 4_000_000:
        raise ValueError("Batch output exceeds 4 MiB; use shorter processor output")
    if body.get("metadata", {}).get("input_truncated") is True:
        raise ValueError(
            "The processor truncated its batch input. Restart or configure it for lossless scope batches; this batch was not marked complete."
        )
    allowed = {row["file_id"]: row for row in documents}

    def references(value):
        if isinstance(value, list):
            return [references(child) for child in value]
        if not isinstance(value, dict):
            return value
        result = {key: references(child) for key, child in value.items()}
        fid = result.get("file_id")
        if fid:
            if fid not in allowed:
                raise ValueError("Tool referenced a document outside this batch")
            row = allowed[fid]
            length = len(row["text"])
            a, b = result.get("char_start"), result.get("char_end")
            if (
                (a is not None and (not isinstance(a, int) or not 0 <= a <= length))
                or (b is not None and (not isinstance(b, int) or not 0 <= b <= length))
                or (a is not None and b is not None and a > b)
            ):
                raise ValueError("Tool citation falls outside its supplied text window")
            if derived:
                # Derived summaries are not original documents or source spans.
                result.pop("file_id", None)
                result.pop("char_start", None)
                result.pop("char_end", None)
                result["source_origin"] = {
                    **result.get("source_origin", {}),
                    "derived_batch": row["batch_id"],
                }
            else:
                for key in ("char_start", "char_end"):
                    if result.get(key) is not None:
                        result[key] += row.get("char_start", 0)
        return result

    if "markdown" in body:
        return {
            "markdown": body["markdown"],
            "citations": references(body.get("citations", [])),
            "artifacts": [],
            "warnings": body.get("warnings", []),
        }
    artifacts = []
    for item in body.get("artifacts", []):
        data = item.get("standard_data") or item.get("data")
        if data is None:
            data = (
                {"artifact_type": "text", "title": item["id"], "text": item["text"]}
                if item.get("text") is not None
                else {
                    "artifact_type": "json",
                    "title": item["id"],
                    "data": item.get("json_data"),
                }
            )
        artifacts.append({"id": item["id"], "data": references(data)})
    if not artifacts:
        raise ValueError("Tool returned no batch results")
    return {"artifacts": artifacts, "warnings": body.get("warnings", [])}


def wiki_text(result: dict) -> str | None:
    if "markdown" in result:
        return result["markdown"]
    values = [
        item["data"]["markdown"]
        for item in result.get("artifacts", [])
        if item["data"].get("artifact_type") == "wiki_markdown"
    ]
    return "\n\n".join(values) if values else None


def reduction_inputs(children: list[dict]) -> list[dict]:
    return [
        {
            "file_id": f"derived-batch-{row['id']}",
            "filename": f"Derived batch {row['id']} summary",
            "text": wiki_text(row["result"]) or "",
            "batch_id": row["id"],
        }
        for row in children
    ]


def reduction_groups(children: Iterable[dict], limits: BatchLimits = BatchLimits()):
    """Group complete intermediate texts; never slice or silently drop a result."""
    group = []
    size = 0
    for child in children:
        text = wiki_text(child["result"])
        if text is None:
            raise ValueError(
                "Wiki reduction requires a Markdown result from each batch"
            )
        if len(text) > limits.characters:
            raise ValueError(
                "An intermediate result exceeds the reduction request budget; lower the tool output length and retry"
            )
        if group and (
            len(group) >= REDUCTION_FAN_IN or size + len(text) > limits.characters
        ):
            yield group
            group = []
            size = 0
        group.append(child)
        size += len(text)
    if group:
        yield group


def result_manifest(run_id: str, summary: dict, *, title: str) -> dict:
    return {
        "artifact_type": "scope_batch_run",
        "title": title,
        "run_id": run_id,
        **summary,
        "description": "Every usable saved-text character was supplied to a batch. Batch-local rankings and selections remain local unless the method declares a reducer.",
    }


class BatchStorage(Protocol):
    """Core adapters persist bounded requests and completed results durably."""

    def summary(self) -> dict: ...
    def reconcile(self) -> None: ...
    def rows(
        self, phase: str, level: int, pending_only: bool = False
    ) -> Iterator[dict]: ...
    def count(self, phase: str, level: int) -> int: ...
    def ensure_reduction(
        self, level: int, index: int, children: list[dict]
    ) -> dict: ...
    def save_result(self, identity: str, result: dict) -> None: ...
    def finish(self, final: dict | None) -> bool | None: ...


def execute_batches(
    storage: BatchStorage,
    invoke: Callable[[dict], Any],
    should_continue: Callable[[], bool],
    report: Callable[[str], None],
) -> bool:
    """Run/replay durable map and reduction rows, stopping at call boundaries.

    Adapters persist a result before the next control check. Retrying an error
    reads those results instead of charging again for completed calls.
    """
    storage.reconcile()
    for row in storage.rows("map", 0, pending_only=True):
        if not should_continue():
            return False
        if row["result"] is None:
            report(
                f"Processing text batch {row['ordinal'] + 1} of {storage.summary()['map_batches']}"
            )
            response = invoke(row)
            storage.save_result(row["id"], normalize_result(response, row["inputs"]))
        if not should_continue():
            return False
    final = None
    if storage.summary()["reduction"] == "wiki":
        phase, level = "map", 0
        while storage.count(phase, level) > 1:
            previous = storage.count(phase, level)
            count = 0
            for index, children in enumerate(
                reduction_groups(
                    storage.rows(phase, level),
                    BatchLimits(
                        characters=storage.summary().get(
                            "batch_characters", BATCH_CHARACTERS
                        )
                    ),
                )
            ):
                if not should_continue():
                    return False
                row = storage.ensure_reduction(level + 1, index, children)
                if row["result"] is None:
                    report(
                        f"Combining summaries · level {level + 1}, batch {index + 1}"
                    )
                    response = invoke(row)
                    storage.save_result(
                        row["id"],
                        normalize_result(response, row["inputs"], derived=True),
                    )
                count += 1
                if not should_continue():
                    return False
            if count >= previous:
                raise ValueError(
                    "The tool summaries are too long to combine within a request. Batch results are retained; use shorter output for a new run."
                )
            phase, level = "reduce", level + 1
        final = next(iter(storage.rows(phase, level)))["result"]
    if not should_continue():
        return False
    if storage.finish(final) is False:
        return False
    report(
        "Every text batch is saved. The combined result and batch details are available."
    )
    return True


def publication_outputs(run_id, summary, title, final, first=None):
    outputs = [
        {
            "id": "batch-results",
            "family": "enrichment",
            "data": result_manifest(
                run_id, summary, title=title + " · Whole-scope results"
            ),
        }
    ]
    selected = final or (first if summary["map_batches"] == 1 else None)
    if selected is not None:
        if wiki_text(selected) is not None:
            outputs.append(
                {
                    "id": "wiki",
                    "family": "synthesis",
                    "data": {
                        "artifact_type": "wiki_markdown",
                        "title": title,
                        "markdown": wiki_text(selected),
                        "citations": selected.get(
                            "citations",
                            next(
                                (
                                    item["data"].get("citations", [])
                                    for item in selected.get("artifacts", [])
                                    if item["data"].get("artifact_type")
                                    == "wiki_markdown"
                                ),
                                [],
                            ),
                        ),
                    },
                }
            )
            outputs.extend(
                {"id": item["id"], "family": "enrichment", "data": item["data"]}
                for item in selected.get("artifacts", [])
                if item["data"].get("artifact_type") != "wiki_markdown"
            )
        else:
            outputs.extend(
                {"id": item["id"], "family": "enrichment", "data": item["data"]}
                for item in selected["artifacts"]
            )
    return outputs


def sampled_keywords(results: Iterable[dict], limit: int = 100) -> list[str]:
    """Bounded, deterministic examples from every batch; never a global ranking."""
    retained: dict[str, str] = {}
    for batch in results:
        result = batch["result"] or {}
        for artifact in result.get("artifacts", []):
            data = artifact["data"]
            if not isinstance(data, dict):
                continue
            for row in data.get("rows", []):
                if not isinstance(row, dict):
                    continue
                candidates = [row.get("keyword") or row.get("term")] + (
                    row.get("keywords") if isinstance(row.get("keywords"), list) else []
                )
                for value in candidates:
                    if (
                        not isinstance(value, str)
                        or not value.strip()
                        or len(value) > 4000
                    ):
                        continue
                    value = value.strip()
                    key = hashlib.sha256(value.casefold().encode()).hexdigest()
                    retained[key] = value
                    if len(retained) > limit:
                        del retained[max(retained)]
    return [retained[key] for key in sorted(retained)]
