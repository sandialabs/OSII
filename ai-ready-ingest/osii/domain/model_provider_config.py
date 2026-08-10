from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_OLLAMA_EMBEDDING_MODEL = "all-minilm"
DEFAULT_OLLAMA_CHAT_MODEL = "llama3.2:1b"

_CAPABILITY_FIELDS = {
    "embedder": "embedding_model",
    "synthesizer": "synthesis_model",
}

_PROCESSOR_NAMES = {
    ("ollama", "embedder"): "ollama.embedder",
    ("ollama", "synthesizer"): "ollama.synthesizer",
    ("openai", "embedder"): "openai.embedder",
    ("openai", "synthesizer"): "openai.synthesizer",
    ("shirty", "embedder"): "corporate.shirty-embedding",
    ("shirty", "synthesizer"): "corporate.shirty-synthesis",
}


def configured_osii_root() -> Path:
    return Path(os.getenv("OSII_ROOT", "./osii-data/.osii")).expanduser().resolve()


def provider_config_path(osii_root: Path | None = None) -> Path:
    return (osii_root or configured_osii_root()) / "state" / "model_providers.json"


def load_provider_records(osii_root: Path | None = None) -> list[dict[str, Any]] | None:
    """Return None when no explicit provider decision has been persisted."""
    path = provider_config_path(osii_root)
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def enabled_providers(osii_root: Path | None = None) -> list[dict[str, Any]]:
    records = load_provider_records(osii_root) or []
    return sorted(
        (item for item in records if item.get("enabled")),
        key=lambda item: (int(item.get("priority", 100)), str(item.get("id", ""))),
    )


def selected_processor(
    capability: str,
    *,
    osii_root: Path | None = None,
) -> str:
    records = load_provider_records(osii_root)
    if records is not None:
        field = _CAPABILITY_FIELDS[capability]
        for provider in enabled_providers(osii_root):
            if not str(provider.get(field) or "").strip():
                continue
            name = _PROCESSOR_NAMES.get((str(provider.get("type")), capability))
            if name:
                return name
        return "local.hashing" if capability == "embedder" else "local.extractive-preview"
    environment_name = "OSII_DEFAULT_EMBEDDER" if capability == "embedder" else "OSII_DEFAULT_SYNTHESIZER"
    fallback = "ollama.embedder" if capability == "embedder" else "ollama.synthesizer"
    return os.getenv(environment_name, fallback).strip() or fallback


def selected_model(
    capability: str,
    *,
    osii_root: Path | None = None,
) -> str:
    records = load_provider_records(osii_root)
    if records is not None:
        field = _CAPABILITY_FIELDS[capability]
        for provider in enabled_providers(osii_root):
            value = str(provider.get(field) or "").strip()
            if value:
                return value
        return "osii-local-hashing-v1" if capability == "embedder" else ""
    if capability == "embedder":
        return os.getenv("EMBEDDING_MODEL", os.getenv("OLLAMA_EMBEDDING_MODEL", DEFAULT_OLLAMA_EMBEDDING_MODEL)).strip() or DEFAULT_OLLAMA_EMBEDDING_MODEL
    return os.getenv("OLLAMA_SYNTHESIS_MODEL", DEFAULT_OLLAMA_CHAT_MODEL).strip() or DEFAULT_OLLAMA_CHAT_MODEL
