"""Grounded chat served by the OSII core.

Chat reads the same scoped search results that the dashboard exposes.  It does
not own persistence and it never bypasses the core's scope or provenance model.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from osii.domain.artifacts.text_spans import get_text_context_by_span
from osii.domain.env_credentials import resolve_env_value
from osii.domain.model_provider_config import DEFAULT_SHIRTY_CHAT_MODEL
from osii.domain.services.search import dashboard_search


router = APIRouter(prefix="/api", tags=["chat"])


class ScopeModel(BaseModel):
    scope_type: str
    folder_id: str | None = None
    collection_id: str | None = None
    file_id: str | None = None


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    query: str = Field(min_length=1)
    scope: ScopeModel
    history: list[ChatTurn] = Field(default_factory=list)
    top_k: int | None = None


class CitationModel(BaseModel):
    file_id: str | None = None
    filename: str | None = None
    source_relpath: str | None = None
    snippet: str | None = None
    chunk_id: str | None = None
    segment_id: str | None = None
    page: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    source_origin: dict[str, Any] | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[CitationModel]
    provider: str
    fallback_used: bool = False
    retrieval_mode: str


@dataclass(frozen=True)
class ChatSettings:
    chat_model: str
    chat_max_results: int
    chat_max_tokens: int
    preferred_search_mode: str
    chat_provider_chain: tuple[str, ...]
    ollama_chat_model: str
    openai_chat_model: str
    ollama_base_url: str
    openai_compatible_base_url: str
    openai_compatible_api_key: str


def _provider_records(osii_root: Path) -> list[dict[str, Any]] | None:
    path = osii_root / "state" / "model_providers.json"
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def get_chat_settings(osii_root: Path) -> ChatSettings:
    primary = os.getenv("CHAT_PROVIDER", "ollama").strip().lower()
    configured_chain = os.getenv("CHAT_PROVIDER_CHAIN", primary)
    chain = tuple(item.strip().lower() for item in configured_chain.split(",") if item.strip())
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    ollama_model = os.getenv("OLLAMA_CHAT_MODEL", "llama3.2:1b").strip() or "llama3.2:1b"
    openai_url = os.getenv("OSII_CHAT_BASE_URL", os.getenv("OSII_MODEL_BASE_URL", "")).rstrip("/")
    openai_model = os.getenv("OSII_CHAT_MODEL", "").strip()
    openai_key = resolve_env_value("OSII_MODEL_API_KEY")[0]
    if primary == "shirty":
        openai_url = f"{os.getenv('OSII_MODEL_BRIDGE_URL', 'http://127.0.0.1:8095').rstrip('/')}/shirty/v1"
        openai_model = os.getenv("SHIRTY_CHAT_MODEL", DEFAULT_SHIRTY_CHAT_MODEL).strip() or DEFAULT_SHIRTY_CHAT_MODEL
        openai_key = ""

    records = _provider_records(osii_root)
    if records is not None:
        enabled = sorted(
            (item for item in records if item.get("enabled")),
            key=lambda item: int(item.get("priority", 100)),
        )
        if not enabled:
            chain = ("extractive",)
            primary = "extractive"
        else:
            configured: list[str] = []
            for item in enabled:
                kind = str(item.get("type") or "").strip().lower()
                if kind == "ollama":
                    configured.append("ollama")
                    ollama_url = str(item.get("base_url") or ollama_url).rstrip("/")
                    ollama_model = str(item.get("chat_model") or ollama_model).strip() or ollama_model
                elif kind == "shirty":
                    configured.append("shirty")
                    openai_url = f"{os.getenv('OSII_MODEL_BRIDGE_URL', 'http://127.0.0.1:8095').rstrip('/')}/shirty/v1"
                    openai_model = str(item.get("chat_model") or DEFAULT_SHIRTY_CHAT_MODEL).strip() or DEFAULT_SHIRTY_CHAT_MODEL
                    # The bundled bridge owns the upstream Shirty credential.
                    openai_key = ""
                elif kind in {"openai", "openai_compatible"}:
                    configured.append("openai")
                    openai_url = str(item.get("base_url") or openai_url).rstrip("/")
                    openai_model = str(item.get("chat_model") or openai_model).strip()
                    credential_env = str(item.get("credential_env") or "OSII_MODEL_API_KEY")
                    openai_key = resolve_env_value(credential_env)[0]
            chain = tuple(dict.fromkeys([*configured, "extractive"]))
            primary = chain[0]

    aliases = {"openai_compatible": "openai"}
    chain = tuple(aliases.get(item, item) for item in chain)
    if "extractive" not in chain:
        chain = (*chain, "extractive")
    return ChatSettings(
        chat_model=os.getenv("CHAT_MODEL", "llama3.2:1b").strip() or "llama3.2:1b",
        chat_max_results=int(os.getenv("CHAT_MAX_RESULTS", "8")),
        chat_max_tokens=int(os.getenv("CHAT_MAX_TOKENS", "900")),
        preferred_search_mode=os.getenv("PREFERRED_SEARCH_MODE", "hybrid"),
        chat_provider_chain=chain,
        ollama_chat_model=ollama_model,
        openai_chat_model=openai_model,
        ollama_base_url=ollama_url,
        openai_compatible_base_url=openai_url,
        openai_compatible_api_key=openai_key,
    )


def _system_prompt() -> str:
    return (
        "You are a careful assistant answering questions over a grounded OSII corpus. "
        "Use the provided retrieval evidence and do not invent facts. "
        "If the evidence is weak or incomplete, say so clearly."
    )


def _user_prompt(*, query: str, scope: dict, history: list[dict], evidence: list[dict]) -> str:
    history_text = "\n".join(
        f"{turn.get('role', 'user').upper()}: {turn.get('content', '')}"
        for turn in history
    ) or "(no prior history)"
    evidence_text = "\n\n".join(
        f"[{index}] file_id={item.get('file_id')} source_relpath={item.get('source_relpath')} "
        f"chunk_id={item.get('chunk_id')} char_start={item.get('char_start')} char_end={item.get('char_end')}\n"
        f"snippet: {item.get('snippet')}"
        for index, item in enumerate(evidence, start=1)
    ) or "(no evidence)"
    return f"""Query:
{query}

Scope:
{scope}

Conversation history:
{history_text}

Evidence:
{evidence_text}

Instructions:
- Answer the query using the evidence above.
- Prefer precise, grounded statements.
- If evidence is insufficient, say so.
- Return only the answer text.
"""


def run_chat_completion(
    *,
    provider: str,
    settings: ChatSettings,
    model: str,
    query: str,
    scope: dict,
    history: list[dict],
    evidence: list[dict],
) -> str:
    if provider == "extractive":
        useful = [item for item in evidence if (item.get("snippet") or "").strip()]
        if not useful:
            return "I could not find grounded text in this scope to answer the question."
        lines = [
            f"- {(item.get('snippet') or '').strip()} "
            f"[{item.get('filename') or item.get('file_id') or 'source'}]"
            for item in useful[:5]
        ]
        return (
            "The locally available evidence most relevant to your question is:\n\n"
            + "\n".join(lines)
            + "\n\nThis answer uses the offline extractive fallback; verify the cited passages for interpretation."
        )

    messages = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": _user_prompt(query=query, scope=scope, history=history, evidence=evidence)},
    ]
    if provider == "ollama":
        response = requests.post(
            f"{settings.ollama_base_url}/api/chat",
            json={"model": model, "stream": False, "messages": messages, "options": {"num_predict": settings.chat_max_tokens}},
            timeout=120,
        )
        response.raise_for_status()
        return (response.json().get("message", {}).get("content") or "").strip() or "[EMPTY_MODEL_OUTPUT]"

    if provider not in {"openai", "shirty"}:
        raise ValueError(f"Unsupported CHAT_PROVIDER: {provider}")
    if not settings.openai_compatible_base_url:
        raise ValueError(f"CHAT_PROVIDER={provider} requires an OpenAI-compatible endpoint.")
    headers = {"Content-Type": "application/json"}
    if settings.openai_compatible_api_key:
        headers["Authorization"] = f"Bearer {settings.openai_compatible_api_key}"
    response = requests.post(
        f"{settings.openai_compatible_base_url}/chat/completions",
        json={"model": model, "messages": messages, "max_tokens": settings.chat_max_tokens},
        headers=headers,
        timeout=120,
    )
    response.raise_for_status()
    choices = response.json().get("choices") or []
    message = choices[0].get("message") if choices and isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else ""
    return str(content or "").strip() or "[EMPTY_MODEL_OUTPUT]"


def _evidence(osii_root: Path, results: list[dict]) -> tuple[list[dict], list[CitationModel]]:
    evidence: list[dict] = []
    citations: list[CitationModel] = []
    for item in results:
        snippet = item.get("snippet")
        if not snippet and item.get("file_id") and item.get("char_start") is not None and item.get("char_end") is not None:
            context = get_text_context_by_span(
                osii_root,
                str(item["file_id"]),
                char_start=int(item["char_start"]),
                char_end=int(item["char_end"]),
                context_chars=300,
            )
            snippet = context.get("match_text") if context else None
        row = {
            "file_id": item.get("file_id"),
            "filename": item.get("filename"),
            "source_relpath": item.get("source_relpath"),
            "snippet": snippet,
            "chunk_id": item.get("chunk_id"),
            "segment_id": item.get("segment_id"),
            "page": item.get("page"),
            "char_start": item.get("char_start"),
            "char_end": item.get("char_end"),
            "source_origin": item.get("source_origin"),
        }
        evidence.append(row)
        citations.append(CitationModel(**row))
    return evidence, citations


@router.get("/chat/health")
def chat_health() -> dict[str, str]:
    return {"status": "ok", "service": "osii-core-chat"}


@router.post("/chat", response_model=ChatResponse)
def chat(request: Request, payload: ChatRequest) -> ChatResponse:
    osii_root = request.app.state.osii_root.resolve()
    settings = get_chat_settings(osii_root)
    scope = payload.scope.model_dump()
    try:
        retrieval_mode, results = dashboard_search(
            osii_root,
            query=payload.query,
            mode=settings.preferred_search_mode,
            top_k=payload.top_k or settings.chat_max_results,
            scope=scope,
        )
    except (RuntimeError, ValueError) as exc:
        # A new OSII installation has an empty chunk manifest until its first
        # processing run. That is a valid chat state, not a failed service.
        if "No valid chunk rows found in chunk manifest" in str(exc):
            retrieval_mode, results = "empty", []
        else:
            raise HTTPException(status_code=502, detail=f"Failed to retrieve from OSII backend: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to retrieve from OSII backend: {exc}") from exc

    evidence, citations = _evidence(osii_root, results)
    failures: list[str] = []
    for provider in settings.chat_provider_chain:
        model = settings.chat_model
        if provider == "ollama":
            model = settings.ollama_chat_model
        elif provider in {"openai", "shirty"}:
            model = settings.openai_chat_model or model
        try:
            answer = run_chat_completion(
                provider=provider,
                settings=settings,
                model=model,
                query=payload.query,
                scope={**scope, "retrieval_mode": retrieval_mode},
                history=[turn.model_dump() for turn in payload.history],
                evidence=evidence,
            )
            return ChatResponse(
                answer=answer,
                citations=citations,
                provider=provider,
                fallback_used=provider != settings.chat_provider_chain[0],
                retrieval_mode=retrieval_mode,
            )
        except Exception as exc:
            failures.append(f"{provider}: {exc}")
    raise HTTPException(status_code=502, detail=f"Failed to generate chat response: {'; '.join(failures)}")
