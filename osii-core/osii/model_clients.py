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

from osii.model_endpoints import ModelEndpoint, endpoint_from_environment
from osii.domain.env_credentials import resolve_env_value
from osii.rag.strategies.http_reranker import create_reranker  # public Core RAG factory


Message = dict[str, object]


class ModelCapabilityUnavailable(RuntimeError):
    """Raised when an optional model-backed capability was not configured."""


class ChatClient(Protocol):
    def complete(self, *, model: str, messages: Sequence[Message], max_tokens: int) -> str: ...


class EmbeddingClient(Protocol):
    def embed(self, *, model: str, texts: Sequence[str]) -> list[list[float]]: ...


class OpenAICompatibleClient:
    """Minimal client for standard OpenAI chat and embedding HTTP endpoints."""

    def __init__(self, base_url: str, api_key: str | None = None, *, credential_env: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or None
        self.credential_env = credential_env

    def _post(self, path: str, payload: dict) -> dict:
        headers = {"Content-Type": "application/json"}
        key = resolve_env_value(self.credential_env)[0] if self.credential_env else self.api_key
        if key:
            headers["Authorization"] = f"Bearer {key}"
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
            if not all(isinstance(row, dict) for row in rows):
                raise ValueError("Invalid embedding response rows")
            if any("index" in row for row in rows):
                indices = [row.get("index") for row in rows]
                if any(type(index) is not int for index in indices) or set(indices) != set(range(len(texts))):
                    raise ValueError("Invalid embedding input indices")
                rows = sorted(rows, key=lambda row: row["index"])
            return [list(row["embedding"]) for row in rows]
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("Embedding service returned invalid vectors.") from exc


def _endpoint(capability: str) -> ModelEndpoint:
    environment = dict(os.environ)
    for name in (f"OSII_{capability.upper()}_API_KEY", "OSII_MODEL_API_KEY", "OPENAI_API_KEY"):
        value, source = resolve_env_value(name)
        environment[name] = value
        if source == "repo_env":
            environment.pop(name + "_FILE", None)
    return endpoint_from_environment(capability, environment=environment)


def create_chat_client() -> ChatClient:
    endpoint = _endpoint("chat")
    base_url = endpoint.base_url
    if not base_url:
        raise ModelCapabilityUnavailable(
            "Model-backed chat and synthesis are not configured. Set "
            "OSII_CHAT_BASE_URL (or OSII_MODEL_BASE_URL) to an "
            "OpenAI-compatible /v1 endpoint."
        )
    return OpenAICompatibleClient(base_url, endpoint.api_key)


def create_embedding_client() -> EmbeddingClient:
    from osii.domain.model_provider_config import selected_processor
    from osii.configuration import models_path, load_models_config, model_connection

    # Setup's saved choice is authoritative for the app, just as it is for
    # readiness tests. Standalone callers without a profile retain env support.
    if models_path().is_file() or os.getenv("OSII_DEFAULT_EMBEDDER", "").strip():
        configuration = load_models_config()
        alias = configuration.get("defaults", {}).get("embedding")
        connection = model_connection(alias) if alias else None
        if connection and connection.get("type") == "openai-compatible":
            key = resolve_env_value(str(connection.get("api_key_env") or "OPENAI_API_KEY"))[0]
            return OpenAICompatibleClient(str(connection.get("base_url") or ""), key, credential_env=str(connection.get("api_key_env") or "OPENAI_API_KEY"))
        processor_name = selected_processor("embedder")
        if processor_name:
            from osii.processors.remote import ProcessorEmbeddingClient, resolve_remote_processor
            return ProcessorEmbeddingClient(resolve_remote_processor(processor_name, "embedder"))

    endpoint = _endpoint("embedding")
    base_url = endpoint.base_url
    if base_url:
        return OpenAICompatibleClient(base_url, endpoint.api_key)
    processor_name = selected_processor("embedder")
    if processor_name:
        from osii.processors.remote import ProcessorEmbeddingClient, resolve_remote_processor
        return ProcessorEmbeddingClient(resolve_remote_processor(processor_name, "embedder"))
    raise ModelCapabilityUnavailable(
        "Embeddings are not configured. Start the bundled embeddings service "
        "or set OSII_EMBEDDING_BASE_URL to an OpenAI-compatible /v1 endpoint."
    )
