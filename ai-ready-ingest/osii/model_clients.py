"""Capability clients for optional OpenAI-compatible model services.

OSII itself has no dependency on a particular corporate model gateway. A
deployment can point these clients at any OpenAI-compatible HTTP endpoint; if
no endpoint is configured, callers receive a clear capability error and can
use the local-first path instead.
"""

from __future__ import annotations

import os
from typing import Protocol, Sequence

import requests

from osii.domain.env_credentials import resolve_env_value


Message = dict[str, object]


class ModelCapabilityUnavailable(RuntimeError):
    """Raised when an optional model-backed capability was not configured."""


class ChatClient(Protocol):
    def complete(self, *, model: str, messages: Sequence[Message], max_tokens: int) -> str: ...


class EmbeddingClient(Protocol):
    def embed(self, *, model: str, texts: Sequence[str]) -> list[list[float]]: ...


class OpenAICompatibleClient:
    """Minimal client for standard OpenAI chat and embedding HTTP endpoints."""

    def __init__(self, base_url: str, api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or None

    def _post(self, path: str, payload: dict) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            response = requests.post(
                f"{self.base_url}{path}", json=payload, headers=headers, timeout=120
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise RuntimeError(f"OpenAI-compatible model request failed: {exc}") from exc

    def complete(self, *, model: str, messages: Sequence[Message], max_tokens: int) -> str:
        payload = self._post(
            "/chat/completions",
            {"model": model, "messages": list(messages), "max_tokens": max_tokens},
        )
        choices = payload.get("choices") or []
        message = choices[0].get("message") if choices and isinstance(choices[0], dict) else None
        if not isinstance(message, dict):
            return ""
        return str(message.get("content") or "").strip()

    def embed(self, *, model: str, texts: Sequence[str]) -> list[list[float]]:
        payload = self._post(
            "/embeddings",
            {"model": model, "input": list(texts), "encoding_format": "float"},
        )
        rows = payload.get("data")
        if not isinstance(rows, list) or len(rows) != len(texts):
            raise RuntimeError("Embedding service returned an invalid response.")
        try:
            return [list(row["embedding"]) for row in rows]
        except (KeyError, TypeError) as exc:
            raise RuntimeError("Embedding service returned invalid vectors.") from exc


def _configured_url(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def create_chat_client() -> ChatClient:
    base_url = _configured_url("OSII_CHAT_BASE_URL", "OSII_MODEL_BASE_URL")
    if not base_url:
        raise ModelCapabilityUnavailable(
            "Model-backed chat and synthesis are not configured. Set "
            "OSII_CHAT_BASE_URL (or OSII_MODEL_BASE_URL) to an "
            "OpenAI-compatible /v1 endpoint."
        )
    return OpenAICompatibleClient(base_url, resolve_env_value("OSII_MODEL_API_KEY")[0])


def create_embedding_client() -> EmbeddingClient:
    from osii.domain.model_provider_config import selected_processor

    base_url = _configured_url("OSII_EMBEDDING_BASE_URL", "OSII_MODEL_BASE_URL")
    if base_url and (os.getenv("OSII_EMBEDDING_BASE_URL", "").strip() or os.getenv("OSII_MODEL_BASE_URL", "").strip()):
        return OpenAICompatibleClient(base_url, resolve_env_value("OSII_EMBEDDING_API_KEY", "OSII_MODEL_API_KEY")[0])
    processor_name = selected_processor("embedder")
    if processor_name:
        from osii.processors.remote import ProcessorEmbeddingClient, resolve_remote_processor
        return ProcessorEmbeddingClient(resolve_remote_processor(processor_name, "embedder"))
    if not base_url:
        raise ModelCapabilityUnavailable(
            "Embeddings are not configured. Start the bundled embeddings service "
            "or set OSII_EMBEDDING_BASE_URL to an OpenAI-compatible /v1 endpoint."
        )
    return OpenAICompatibleClient(base_url, resolve_env_value("OSII_EMBEDDING_API_KEY", "OSII_MODEL_API_KEY")[0])
