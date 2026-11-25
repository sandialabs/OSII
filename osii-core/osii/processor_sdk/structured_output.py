"""Shared Chat Completions helpers for processors that need typed JSON."""

from __future__ import annotations

import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError


Output = TypeVar("Output", bound=BaseModel)
_JSON_FENCE = re.compile(r"```(?:json)?[^\S\n]*\n(.*)\n```", re.IGNORECASE | re.DOTALL)


def json_schema_format(output: type[BaseModel]) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": output.__name__,
            "strict": True,
            "schema": output.model_json_schema(),
        },
    }


def chat_completion_metadata(response: Any, model: str) -> dict[str, Any]:
    extra = getattr(response, "model_extra", None) or {}
    gateway = extra.get("osii") or {}
    metadata = {
        "model": getattr(response, "model", None) or model,
        "model_connection": gateway.get("connection") or model,
        "provider_type": gateway.get("provider_type"),
        "finish_reason": getattr(response.choices[0], "finish_reason", None)
        if response.choices else None,
    }
    if usage := getattr(response, "usage", None):
        metadata["usage"] = {
            key: getattr(usage, key, None)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        }
    return metadata


def parse_structured_response(
    response: Any,
    output: type[Output],
    *,
    model: str,
    batch_id: str | None = None,
) -> Output:
    """Validate one model reply. Keep generated content out of diagnostics."""
    meta = chat_completion_metadata(response, model)
    reason = meta["finish_reason"] or "unknown"
    batch = f", batch {batch_id}" if batch_id is not None else ""
    context = f"{meta['model']} (connection {meta['model_connection']}{batch}, stop reason {reason})"
    if usage := meta.get("usage"):
        if usage.get("completion_tokens") is not None:
            context += f", {usage['completion_tokens']} output tokens"
    if reason == "length":
        raise ValueError(
            f"{context}. The response reached its output token limit. "
            "Increase the output token limit or use smaller input batches."
        )
    choice = response.choices[0] if response.choices else None
    message = choice.message if choice else None
    if reason == "content_filter" or getattr(message, "refusal", None):
        raise ValueError(f"{context}. The model declined to generate the requested JSON.")
    content = getattr(message, "content", None)
    if not isinstance(content, str) or not content.strip():
        raise ValueError(f"{context}. The model returned no JSON. Check the model or try a different one.")
    text = content.strip()
    if fenced := _JSON_FENCE.fullmatch(text):
        text = fenced[1]
    try:
        return output.model_validate_json(text, strict=True)
    except ValidationError as exc:
        error = exc.errors(include_input=False)[0]["type"]
        detail = "invalid JSON" if error == "json_invalid" else "JSON that did not match the required schema"
        raise ValueError(
            f"{context}. The model returned {detail}. Try a model that supports structured output."
        ) from None
