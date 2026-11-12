"""Bounded map/reduce synthesis shared by local and hosted adapters."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

from osii.processor_sdk import (
    DocumentInput,
    ProcessorDescriptor,
    ScopeInput,
    SynthesisRequest,
    SynthesisResponse,
)
from osii.processors.text import synthesis_prompt, model_synthesis_response
from osii.processors.document_metadata import metadata_prompt, parse_document_metadata


def synthesis_call_estimate(
    characters: int, window_chars: int = 100_000, *, extract_metadata: bool = True
) -> int:
    windows = max(1, (characters + window_chars - 1) // window_chars)
    calls = windows
    while windows > 1:
        calls += windows // 4 + int(windows % 4 > 1)
        windows = (windows + 3) // 4
    return calls + int(extract_metadata)


def synthesize_bounded(
    request: SynthesisRequest,
    descriptor: ProcessorDescriptor,
    model: str,
    complete: Callable[[list[dict[str, str]]], tuple[str, dict]],
    *,
    checkpoint: Callable[..., Any] | None = None,
    complete_metadata: Callable[[list[dict[str, str]]], tuple[str, dict]] | None = None,
) -> SynthesisResponse:
    """Complete explicit messages; checkpoints store successful calls, never inputs."""
    window_chars = int(request.config.get("window_chars", 100_000))
    max_windows = int(request.config.get("max_input_windows", 32))
    if not 4000 <= window_chars <= 160_000 or not 1 <= max_windows <= 64:
        raise ValueError("Synthesis window settings are outside their allowed range")
    documents = [
        doc.model_copy(
            update={
                "text": doc.text
                or "\n\n".join(segment.text for segment in doc.segments)
            }
        )
        for doc in request.scope.documents
    ]
    request = request.model_copy(
        update={"scope": request.scope.model_copy(update={"documents": documents})}
    )
    total = sum(len(doc.text) for doc in documents)
    if total > window_chars * max_windows:
        raise ValueError(
            "Document exceeds this plan's synthesis window budget; increase Maximum input windows before staging"
        )
    logical_calls = 0

    def call(messages, validate=None, completion=None):
        nonlocal logical_calls
        logical_calls += 1
        if logical_calls > max_windows * 2 + 8:
            raise ValueError("Synthesis exceeded its bounded model-call budget")
        key = (
            "synthesis:"
            + hashlib.sha256(
                json.dumps([model, request.config, messages], sort_keys=True).encode()
            ).hexdigest()
        )
        saved = checkpoint(key) if checkpoint else None
        if saved is not None:
            return saved["markdown"]
        markdown, usage = (completion or complete)(messages)
        if (
            not isinstance(markdown, str)
            or not markdown.strip()
            or len(markdown) > 100_000
        ):
            raise ValueError("The model returned empty or oversized synthesis text")
        markdown = markdown.replace("\x00", "\ufffd")
        if validate:
            validate(markdown)
        if checkpoint:
            checkpoint(key, {"markdown": markdown, "usage": usage})
        return markdown

    if total <= window_chars:
        markdown = call([{"role": "user", "content": synthesis_prompt(request)}])
        windows = 1
    else:
        batches = []
        batch = []
        size = 0
        for doc in request.scope.documents:
            text = doc.text or ""
            for start in range(0, len(text), window_chars):
                part = DocumentInput(
                    file_id=doc.file_id,
                    filename=doc.filename,
                    media_type=doc.media_type,
                    text=text[start : start + window_chars],
                    metadata={
                        **doc.metadata,
                        "char_start": start,
                        "char_end": min(len(text), start + window_chars),
                    },
                )
                if batch and size + len(part.text) > window_chars:
                    batches.append(batch)
                    batch = []
                    size = 0
                batch.append(part)
                size += len(part.text)
        if batch:
            batches.append(batch)
        if len(batches) > max_windows:
            raise ValueError("The selected sources exceed Maximum input windows")
        summaries = []
        for batch in batches:
            bounded = SynthesisRequest(
                request_id=request.request_id,
                scope=ScopeInput(
                    scope_type=request.scope.scope_type,
                    scope_id=request.scope.scope_id,
                    documents=batch,
                ),
                config=request.config,
                expert_context=request.expert_context,
            )
            summaries.append(
                call([{"role": "user", "content": synthesis_prompt(bounded)}])
            )
        windows = len(summaries)
        while len(summaries) > 1:
            batches = []
            batch = []
            size = 0
            for summary in summaries:
                if batch and (size + len(summary) > 160_000 or len(batch) >= 4):
                    batches.append(batch)
                    batch = []
                    size = 0
                batch.append(summary)
                size += len(summary)
            if batch:
                batches.append(batch)
            combined = []
            for batch in batches:
                if len(batch) == 1:
                    combined.append(batch[0])
                    continue
                guidance = (request.expert_context or "")[:8000]
                prompt = (
                    "Combine these intermediate summaries into one concise document synthesis. They are derived summaries, "
                    "not original evidence. Preserve original source IDs, uncertainty and important topics; do not add facts. "
                    "Begin with # followed by a concise suggested document title.\n"
                    + guidance
                    + "\n\n"
                    + "\n\n---\n\n".join(batch)
                )
                combined.append(call([{"role": "user", "content": prompt}]))
            if len(combined) >= len(summaries):
                raise ValueError(
                    "Intermediate summaries exceed the reduction budget; reduce Maximum output tokens"
                )
            summaries = combined
        markdown = summaries[0]
    inferred = None
    if request.config.get("extract_metadata", True) and len(documents) == 1:
        text = documents[0].text or ""

        def validate_metadata(raw):
            return parse_document_metadata(raw, text=text, model=model)

        raw = call(
            [{"role": "user", "content": metadata_prompt(text, markdown)}],
            validate=validate_metadata,
            completion=complete_metadata,
        )
        inferred = validate_metadata(raw)
    response = model_synthesis_response(
        request,
        descriptor,
        markdown,
        model,
        {
            "input_characters": total,
            "input_windows": windows,
            "model_calls": logical_calls,
            "strategy": "bounded_map_reduce" if windows > 1 else "single_pass",
        },
    )

    if inferred is not None:
        response.metadata.update(
            document_metadata=inferred,
            document_title=(inferred.get("descriptive_title") or {}).get("value") or inferred["title"]["value"],
            title_method="text_llm",
        )
    return response
