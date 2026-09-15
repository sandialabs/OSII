from __future__ import annotations

import json
import os
from pathlib import Path
import threading
import time
from typing import Any
import uuid

import requests
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from app.env_credentials import resolve_secret

from osii.processor_sdk import (
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
from osii.configuration import load_models_config, model_connection
from osii.model_gateway_tokens import verify_model_gateway_token


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

    def configured_base_url(self, capability: str | None = None) -> str:
        configured = _configured_provider(self.provider, capability)
        if configured and configured.get("base_url"):
            return str(configured["base_url"]).rstrip("/")
        if self.provider == "ollama":
            return os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        return (
            os.getenv("OPENAI_BASE_URL", "").strip()
            or os.getenv("OSII_MODEL_BASE_URL", "").strip()
        ).rstrip("/")

    def headers(
        self,
        *,
        content_type: str | None = "application/json",
        capability: str | None = None,
    ) -> dict[str, str]:
        headers = {"Content-Type": content_type} if content_type else {}
        if self.provider == "ollama":
            return headers
        configured = _configured_provider(self.provider, capability) or {}
        configured_env = str(configured.get("credential_env") or "").strip()
        env_names = [
            configured_env,
            "OPENAI_API_KEY",
            os.getenv("OSII_MODEL_API_KEY_ENV", "OSII_MODEL_API_KEY"),
        ]
        key = resolve_secret(*env_names)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict | None = None,
        timeout: float = 60,
        capability: str | None = None,
    ) -> dict:
        base_url = self.configured_base_url(capability)
        if not base_url:
            raise ValueError("Provider base URL is not configured.")
        self.breaker.before()
        try:
            response = requests.request(
                method,
                f"{base_url}{path}",
                json=payload,
                headers=self.headers(capability=capability),
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
        payload = CLIENTS["ollama"].request("GET", "/api/tags", timeout=8, capability="embedding")
        rows = [item for item in payload.get("models", []) if isinstance(item, dict)]
        _OLLAMA_MODEL_CACHE = (time.monotonic(), rows)
    record = next((item for item in rows if item.get("model") == model or item.get("name") == model), None)
    return str(record.get("digest")) if record and record.get("digest") else None


def _configured_provider(provider: str, capability: str | None = None) -> dict[str, Any] | None:
    configuration = load_models_config()
    defaults = configuration.get("defaults", {})
    models = configuration.get("models", {})
    expected_type = "ollama-local" if provider == "ollama" else "openai-compatible"
    candidates = (
        ("embedding", "embedding_model"),
        ("synthesis", "synthesis_model"),
        ("chat", "chat_model"),
    )
    if capability:
        candidates = tuple(item for item in candidates if item[0] == capability)
    for candidate_capability, field in candidates:
        alias = str(defaults.get(candidate_capability) or "")
        record = models.get(alias) if isinstance(models, dict) else None
        if isinstance(record, dict) and record.get("enabled", True) and record.get("type") == expected_type:
            return {
                "id": alias,
                "type": provider,
                "base_url": record.get("base_url"),
                "credential_env": record.get("api_key_env"),
                field: record.get("model"),
                "enabled": True,
            }
    root = Path(os.getenv("OSII_ROOT", "./osii-data/.osii"))
    try:
        records = json.loads((root / "state" / "model_providers.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    candidates = sorted((item for item in records if item.get("type") == provider and item.get("enabled")), key=lambda item: int(item.get("priority", 100)))
    return candidates[0] if candidates else None


def _model(provider: str, capability: str, config: dict[str, Any] | None = None) -> str:
    explicit = str((config or {}).get("model") or "").strip()
    configured = _configured_provider(provider, capability) or {}
    selected = str(configured.get(f"{capability}_model") or "").strip()
    prefix = {"ollama": "OLLAMA", "openai": "OPENAI"}[provider]
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
            payload = CLIENTS[self.provider].request("POST", "/api/embed", payload={"model": model, "input": texts, "truncate": False}, capability="embedding")
            rows = payload.get("embeddings")
            model_digest = _ollama_model_digest(model)
        else:
            try:
                payload = CLIENTS[self.provider].request("POST", "/embeddings", payload={"model": model, "input": texts, "encoding_format": "float"}, capability="embedding")
            except ValueError:
                # Some otherwise OpenAI-compatible providers reject the optional
                # encoding_format field. Retry the same vector space request
                # using only the required model and input fields.
                payload = CLIENTS[self.provider].request("POST", "/embeddings", payload={"model": model, "input": texts}, capability="embedding")
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
            payload = CLIENTS[self.provider].request("POST", "/api/chat", payload={"model": model, "messages": messages, "stream": False, "options": {"num_predict": max_tokens, "temperature": temperature}}, timeout=180, capability="synthesis")
            markdown = payload.get("message", {}).get("content", "")
        else:
            payload = CLIENTS[self.provider].request("POST", "/chat/completions", payload={"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}, timeout=180, capability="synthesis")
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
    temperature: float | None = None


class GatewayEmbeddingRequest(BaseModel):
    model: str
    input: str | list[str]
    encoding_format: str | None = None


app = FastAPI(title="OSII Model Provider Bridge", version="0.1.0")
for provider in ("ollama", "openai"):
    app.mount(f"/{provider}/embedder", create_processor_app(ProviderEmbedder(provider)))
for provider in ("ollama", "openai"):
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


_GATEWAY_COUNTS: dict[str, int] = {}
_GATEWAY_REVOKED: dict[str, int] = {}
_GATEWAY_COUNTS_LOCK = threading.Lock()


def _gateway_claims(authorization: str | None) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="A Model Gateway job token is required")
    try:
        claims = verify_model_gateway_token(authorization.split(" ", 1)[1].strip())
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    identifier = str(claims.get("jti") or "")
    with _GATEWAY_COUNTS_LOCK:
        now = int(time.time())
        for expired in [key for key, expiration in _GATEWAY_REVOKED.items() if expiration <= now]:
            _GATEWAY_REVOKED.pop(expired, None)
        if identifier in _GATEWAY_REVOKED:
            raise HTTPException(status_code=401, detail="Model Gateway job token is no longer active")
        count = _GATEWAY_COUNTS.get(identifier, 0) + 1
        if count > int(claims.get("max_requests", 64)):
            raise HTTPException(status_code=429, detail="Model Gateway request allowance exhausted")
        _GATEWAY_COUNTS[identifier] = count
    return claims


@app.post("/v1/tokens/revoke")
def revoke_gateway_token(authorization: str | None = Header(default=None)) -> dict[str, bool]:
    """End one job grant without accepting a broader administrative secret."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="A Model Gateway job token is required")
    try:
        claims = verify_model_gateway_token(authorization.split(" ", 1)[1].strip())
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    identifier = str(claims.get("jti") or "")
    with _GATEWAY_COUNTS_LOCK:
        _GATEWAY_REVOKED[identifier] = int(claims["exp"])
        _GATEWAY_COUNTS.pop(identifier, None)
    return {"revoked": True}


def _bound_connection(claims: dict[str, Any], capability: str, requested: str) -> tuple[str, dict[str, Any]]:
    alias = str(claims["bindings"].get(capability) or "")
    if not alias or requested != alias:
        raise HTTPException(status_code=403, detail=f"This job is not allowed to use {requested!r} for {capability}")
    connection = model_connection(alias)
    if connection is None:
        raise HTTPException(status_code=503, detail=f"Model connection {alias!r} is unavailable")
    if capability not in connection.get("capabilities", []):
        raise HTTPException(status_code=422, detail=f"Model connection {alias!r} does not support {capability}")
    return alias, connection


def _connection_client(connection: dict[str, Any]) -> ProviderHTTP:
    provider_type = str(connection.get("type") or "")
    provider = "ollama" if provider_type == "ollama-local" else "openai"
    client = ProviderHTTP(provider)
    configured_url = str(connection.get("base_url") or "").rstrip("/")
    if provider == "ollama" and os.getenv("OLLAMA_BASE_URL", "").strip():
        configured_url = os.environ["OLLAMA_BASE_URL"].rstrip("/")
    client._gateway_base_url = configured_url  # type: ignore[attr-defined]
    client._gateway_credential_env = str(connection.get("api_key_env") or "OPENAI_API_KEY")  # type: ignore[attr-defined]
    return client


def _gateway_request(client: ProviderHTTP, method: str, path: str, *, payload: dict, timeout: float) -> dict:
    base_url = str(getattr(client, "_gateway_base_url", "") or client.configured_base_url()).rstrip("/")
    if not base_url:
        raise HTTPException(status_code=503, detail="The selected model connection has no endpoint URL")
    credential_env = str(getattr(client, "_gateway_credential_env", "") or "OPENAI_API_KEY")
    key = resolve_secret(credential_env)
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        response = requests.request(method, f"{base_url}{path}", json=payload, headers=headers, timeout=(3, timeout))
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Selected model connection failed: {exc}") from exc


@app.get("/v1/models")
def gateway_models(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    claims = _gateway_claims(authorization)
    aliases = sorted(set(map(str, claims["bindings"].values())))
    return {"object": "list", "data": [{"id": alias, "object": "model", "owned_by": "osii"} for alias in aliases]}


@app.post("/v1/chat/completions")
def gateway_chat(
    request: ChatRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    if not request.model:
        raise HTTPException(status_code=422, detail="model must be an OSII model connection name")
    claims = _gateway_claims(authorization)
    alias, connection = _bound_connection(claims, "chat", request.model)
    client = _connection_client(connection)
    actual_model = str(connection.get("model") or "")
    provider_type = str(connection.get("type") or "")
    if provider_type == "ollama-local":
        options = {"num_predict": request.max_tokens}
        if request.temperature is not None:
            options["temperature"] = request.temperature
        payload = _gateway_request(
            client,
            "POST",
            "/api/chat",
            payload={"model": actual_model, "messages": request.messages, "stream": False, "options": options},
            timeout=180,
        )
        content = payload.get("message", {}).get("content", "")
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": actual_model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "osii": {"connection": alias, "provider_type": provider_type},
        }
    provider_payload: dict[str, Any] = {
        "model": actual_model,
        "messages": request.messages,
        "max_tokens": request.max_tokens,
    }
    if request.temperature is not None:
        provider_payload["temperature"] = request.temperature
    payload = _gateway_request(client, "POST", "/chat/completions", payload=provider_payload, timeout=180)
    payload["osii"] = {"connection": alias, "provider_type": provider_type}
    return payload


@app.post("/v1/embeddings")
def gateway_embeddings(
    request: GatewayEmbeddingRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    claims = _gateway_claims(authorization)
    alias, connection = _bound_connection(claims, "embedding", request.model)
    client = _connection_client(connection)
    actual_model = str(connection.get("model") or "")
    values = [request.input] if isinstance(request.input, str) else request.input
    provider_type = str(connection.get("type") or "")
    if provider_type == "ollama-local":
        payload = _gateway_request(
            client,
            "POST",
            "/api/embed",
            payload={"model": actual_model, "input": values, "truncate": False},
            timeout=120,
        )
        rows = payload.get("embeddings") or []
        data = [{"object": "embedding", "index": index, "embedding": row} for index, row in enumerate(rows)]
        return {"object": "list", "model": actual_model, "data": data, "osii": {"connection": alias, "provider_type": provider_type}}
    provider_payload: dict[str, Any] = {"model": actual_model, "input": values}
    if request.encoding_format:
        provider_payload["encoding_format"] = request.encoding_format
    payload = _gateway_request(client, "POST", "/embeddings", payload=provider_payload, timeout=120)
    payload["osii"] = {"connection": alias, "provider_type": provider_type}
    return payload


@app.post("/{provider}/v1/chat/completions")
def chat(provider: str, request: ChatRequest) -> dict[str, Any]:
    if provider not in CLIENTS:
        raise HTTPException(status_code=404, detail="Unknown provider")
    model = request.model or _model(provider, "chat")
    if provider == "ollama":
        payload = CLIENTS[provider].request("POST", "/api/chat", payload={"model": model, "messages": request.messages, "stream": False}, timeout=180, capability="chat")
        content = payload.get("message", {}).get("content", "")
        return {"model": model, "provider": provider, "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}]}
    payload = CLIENTS[provider].request("POST", "/chat/completions", payload={"model": model, "messages": request.messages, "max_tokens": request.max_tokens}, timeout=180, capability="chat")
    payload["provider"] = provider
    return payload
