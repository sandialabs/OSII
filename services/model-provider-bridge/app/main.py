from __future__ import annotations

import json
import os
from pathlib import Path
import threading
import time
from typing import Any

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from osii_processor_sdk import (
    Capability,
    Embedder,
    EmbeddingRequest,
    EmbeddingResponse,
    EmbeddingVector,
    ProcessorDescriptor,
    ProcessorKind,
    ProvenanceRef,
    SynthesisRequest,
    SynthesisResponse,
    Synthesizer,
    create_processor_app,
)


class CircuitBreaker:
    def __init__(self, failures: int = 2, cooldown: float = 30.0) -> None:
        self.threshold = failures
        self.cooldown = cooldown
        self.failures = 0
        self.open_until = 0.0
        self.lock = threading.Lock()

    def before(self) -> None:
        with self.lock:
            if self.open_until > time.monotonic():
                raise RuntimeError("Provider circuit is temporarily open after repeated failures.")

    def success(self) -> None:
        with self.lock:
            self.failures = 0
            self.open_until = 0.0

    def failure(self) -> None:
        with self.lock:
            self.failures += 1
            if self.failures >= self.threshold:
                self.open_until = time.monotonic() + self.cooldown


class ProviderHTTP:
    def __init__(self, provider: str) -> None:
        self.provider = provider
        self.breaker = CircuitBreaker()

    @property
    def base_url(self) -> str:
        configured = _configured_provider(self.provider)
        if configured and configured.get("base_url"):
            return str(configured["base_url"]).rstrip("/")
        if self.provider == "ollama":
            return os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        return os.getenv("OSII_MODEL_BASE_URL", "").rstrip("/")

    def headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        configured = _configured_provider(self.provider) or {}
        env_name = str(configured.get("credential_env") or os.getenv("OSII_MODEL_API_KEY_ENV", "OSII_MODEL_API_KEY"))
        key = os.getenv(env_name, "")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    def request(self, method: str, path: str, *, payload: dict | None = None, timeout: float = 60) -> dict:
        if not self.base_url:
            raise ValueError("Provider base URL is not configured.")
        self.breaker.before()
        try:
            response = requests.request(
                method,
                f"{self.base_url}{path}",
                json=payload,
                headers=self.headers(),
                timeout=(3.0, timeout),
            )
            response.raise_for_status()
            data = response.json()
        except requests.HTTPError as exc:
            detail = (exc.response.text or str(exc))[:1000]
            if 400 <= exc.response.status_code < 500:
                # Processor API reports invalid provider inputs as 422 so the
                # caller can adjust them instead of treating them as downtime
                # or opening the availability circuit breaker.
                raise ValueError(
                    f"{self.provider} rejected the request: HTTP "
                    f"{exc.response.status_code} - {detail}"
                ) from exc
            self.breaker.failure()
            raise RuntimeError(f"{self.provider} request failed: {exc} - {detail}") from exc
        except (requests.RequestException, ValueError) as exc:
            self.breaker.failure()
            raise RuntimeError(f"{self.provider} request failed: {exc}") from exc
        self.breaker.success()
        return data


CLIENTS = {name: ProviderHTTP(name) for name in ("ollama", "openai")}
_OLLAMA_MODEL_CACHE: tuple[float, list[dict[str, Any]]] = (0.0, [])
DEFAULT_SYNTHESIS_INSTRUCTIONS = (
    "Write a concise grounded Markdown synthesis. Cite source file IDs in square "
    "brackets. Do not introduce facts absent from the sources."
)


def _ollama_model_digest(model: str) -> str | None:
    global _OLLAMA_MODEL_CACHE
    cached_at, rows = _OLLAMA_MODEL_CACHE
    if time.monotonic() - cached_at > 60:
        payload = CLIENTS["ollama"].request("GET", "/api/tags", timeout=8)
        rows = [item for item in payload.get("models", []) if isinstance(item, dict)]
        _OLLAMA_MODEL_CACHE = (time.monotonic(), rows)
    record = next((item for item in rows if item.get("model") == model or item.get("name") == model), None)
    return str(record.get("digest")) if record and record.get("digest") else None


def _configured_provider(provider: str) -> dict[str, Any] | None:
    root = Path(os.getenv("OSII_ROOT", "./osii-data/.osii"))
    try:
        records = json.loads((root / "state" / "model_providers.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    candidates = sorted((item for item in records if item.get("type") == provider and item.get("enabled")), key=lambda item: int(item.get("priority", 100)))
    return candidates[0] if candidates else None


def _model(provider: str, capability: str, config: dict[str, Any] | None = None) -> str:
    explicit = str((config or {}).get("model") or "").strip()
    configured = _configured_provider(provider) or {}
    selected = str(configured.get(f"{capability}_model") or "").strip()
    prefix = "OLLAMA" if provider == "ollama" else "OSII"
    default = ""
    if provider == "ollama":
        default = "all-minilm" if capability == "embedding" else "llama3.2:1b"
    value = explicit or selected or os.getenv(f"{prefix}_{capability.upper()}_MODEL", "").strip() or default
    if not value:
        raise ValueError(f"No {capability} model is selected for {provider}.")
    return value


class ProviderEmbedder(Embedder):
    def __init__(self, provider: str) -> None:
        self.provider = provider
        self.descriptor = ProcessorDescriptor(
            name=f"{provider}.embedder",
            version="1.0.0",
            display_name=f"{provider.title()} Embedder",
            description=f"Processor API adapter for an explicitly selected {provider} embedding model.",
            kind=ProcessorKind.EMBEDDER,
            capabilities=Capability(output_kinds=["embedding_vector"]),
        )

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        model = _model(self.provider, "embedding", request.config)
        texts = [item.text for item in request.inputs]
        if self.provider == "ollama":
            payload = CLIENTS[self.provider].request("POST", "/api/embed", payload={"model": model, "input": texts, "truncate": False})
            rows = payload.get("embeddings")
            model_digest = _ollama_model_digest(model)
        else:
            payload = CLIENTS[self.provider].request("POST", "/embeddings", payload={"model": model, "input": texts, "encoding_format": "float"})
            rows = [row.get("embedding") for row in payload.get("data", [])]
            model_digest = None
        if not isinstance(rows, list) or len(rows) != len(texts):
            raise ValueError("Provider returned an invalid number of embedding vectors.")
        vectors = []
        for item, row in zip(request.inputs, rows, strict=True):
            if not isinstance(row, list) or not row:
                raise ValueError("Provider returned an empty or invalid embedding vector.")
            vectors.append(EmbeddingVector(id=item.id, vector=[float(value) for value in row], dimensions=len(row)))
        return EmbeddingResponse(
            request_id=request.request_id,
            processor=self.descriptor,
            model=str(payload.get("model") or model),
            vectors=vectors,
            normalized=self.provider == "ollama",
            metadata={"provider": self.provider, "endpoint_type": "ollama-native" if self.provider == "ollama" else "openai-compatible", "semantic": True, **({"model_digest": model_digest} if model_digest else {})},
        )


def _scope_prompt(request: SynthesisRequest) -> str:
    sources = []
    for document in request.scope.documents:
        text = document.text or "\n\n".join(segment.text for segment in document.segments)
        sources.append(f"SOURCE {document.file_id or document.filename}:\n{text}")
    instructions = str(
        request.config.get("instructions")
        or DEFAULT_SYNTHESIS_INSTRUCTIONS
    ).strip()
    context = str(request.expert_context or "").strip()
    guidance = f"\n\nADDITIONAL GUIDANCE:\n{context}" if context else ""
    return f"{instructions}{guidance}\n\n" + "\n\n".join(sources)


class ProviderSynthesizer(Synthesizer):
    def __init__(self, provider: str) -> None:
        self.provider = provider
        self.descriptor = ProcessorDescriptor(
            name=f"{provider}.synthesizer",
            version="1.0.0",
            display_name=f"{provider.title()} Synthesizer",
            description=f"Processor API adapter for an explicitly selected {provider} chat model.",
            kind=ProcessorKind.SYNTHESIZER,
            capabilities=Capability(scope_types=["object", "folder", "collection", "root"], output_kinds=["wiki_markdown"]),
            config_schema={
                "type": "object",
                "properties": {
                    "instructions": {
                        "type": "string", "title": "Synthesis prompt",
                        "description": "Instructions placed before the grounded source material.",
                        "default": DEFAULT_SYNTHESIS_INSTRUCTIONS, "format": "textarea",
                    },
                    "temperature": {
                        "type": "number", "title": "Temperature",
                        "description": "Lower values make synthesis more repeatable.",
                        "minimum": 0, "maximum": 2, "default": 0.2,
                    },
                    "max_tokens": {
                        "type": "integer", "title": "Maximum output tokens",
                        "minimum": 256, "maximum": 4000, "default": 1200,
                    },
                },
                "additionalProperties": False,
            },
        )

    def synthesize(self, request: SynthesisRequest) -> SynthesisResponse:
        model = _model(self.provider, "synthesis", request.config)
        messages = [{"role": "user", "content": _scope_prompt(request)}]
        max_tokens = max(256, min(int(request.config.get("max_tokens", 1200)), 4000))
        temperature = max(0.0, min(float(request.config.get("temperature", 0.2)), 2.0))
        if self.provider == "ollama":
            payload = CLIENTS[self.provider].request("POST", "/api/chat", payload={"model": model, "messages": messages, "stream": False, "options": {"num_predict": max_tokens, "temperature": temperature}}, timeout=180)
            markdown = payload.get("message", {}).get("content", "")
        else:
            payload = CLIENTS[self.provider].request("POST", "/chat/completions", payload={"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}, timeout=180)
            choices = payload.get("choices") or []
            markdown = choices[0].get("message", {}).get("content", "") if choices else ""
        if not str(markdown).strip():
            raise ValueError("Provider returned empty synthesis text.")
        citations = [ProvenanceRef(file_id=doc.file_id) for doc in request.scope.documents if doc.file_id]
        return SynthesisResponse(request_id=request.request_id, processor=self.descriptor, markdown=str(markdown).strip(), citations=citations, metadata={"provider": self.provider, "endpoint_type": "ollama-native" if self.provider == "ollama" else "openai-compatible", "model": model})


class ChatRequest(BaseModel):
    model: str | None = None
    messages: list[dict[str, Any]] = Field(min_length=1)
    max_tokens: int = 900


app = FastAPI(title="OSII Model Provider Bridge", version="0.1.0")
for provider in ("ollama", "openai"):
    app.mount(f"/{provider}/embedder", create_processor_app(ProviderEmbedder(provider)))
    app.mount(f"/{provider}/synthesizer", create_processor_app(ProviderSynthesizer(provider)))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/providers")
def providers() -> dict[str, Any]:
    results: dict[str, Any] = {}
    for provider, client in CLIENTS.items():
        try:
            path = "/api/tags" if provider == "ollama" else "/models"
            payload = client.request("GET", path, timeout=8)
            models = payload.get("models") or payload.get("data") or []
            results[provider] = {"available": True, "models": [item.get("model") or item.get("name") or item.get("id") for item in models]}
        except Exception as exc:
            results[provider] = {"available": False, "models": [], "detail": str(exc)}
    return {"providers": results}


@app.post("/{provider}/v1/chat/completions")
def chat(provider: str, request: ChatRequest) -> dict[str, Any]:
    if provider not in CLIENTS:
        raise HTTPException(status_code=404, detail="Unknown provider")
    model = request.model or _model(provider, "chat")
    if provider == "ollama":
        payload = CLIENTS[provider].request("POST", "/api/chat", payload={"model": model, "messages": request.messages, "stream": False}, timeout=180)
        content = payload.get("message", {}).get("content", "")
        return {"model": model, "provider": provider, "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}]}
    payload = CLIENTS[provider].request("POST", "/chat/completions", payload={"model": model, "messages": request.messages, "max_tokens": request.max_tokens}, timeout=180)
    payload["provider"] = provider
    return payload
