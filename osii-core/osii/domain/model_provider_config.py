from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from osii.configuration import load_models_config, model_connection

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
    configuration = load_models_config(osii_root)
    defaults = configuration.get("defaults", {})
    config_capability = "embedding" if capability == "embedder" else "synthesis"
    alias = str(defaults.get(config_capability) or "")
    connection = model_connection(alias, osii_root) if alias else None
    if connection:
        provider_type = str(connection.get("type") or "")
        provider = "ollama" if provider_type == "ollama-local" else "openai"
        return _PROCESSOR_NAMES.get((provider, capability), "")
    return "local.hashing" if capability == "embedder" else "local.extractive-preview"


def selected_model(
    capability: str,
    *,
    osii_root: Path | None = None,
) -> str:
    configuration = load_models_config(osii_root)
    config_capability = "embedding" if capability == "embedder" else "synthesis"
    alias = str(configuration.get("defaults", {}).get(config_capability) or "")
    connection = model_connection(alias, osii_root) if alias else None
    if connection:
        return str(connection.get("model") or "")
    return "osii-local-hashing-v1" if capability == "embedder" else ""


def processor_model(
    processor_name: str,
    capability: str,
    *,
    osii_root: Path | None = None,
) -> str:
    """Return the configured model for one provider-backed processor."""
    provider_type = next(
        (
            provider
            for (provider, kind), name in _PROCESSOR_NAMES.items()
            if kind == capability and name == processor_name
        ),
        "",
    )
    if not provider_type:
        return ""

    configuration = load_models_config(osii_root)
    config_capability = "embedding" if capability == "embedder" else "synthesis"
    alias = str(configuration.get("defaults", {}).get(config_capability) or "")
    connection = model_connection(alias, osii_root) if alias else None
    expected_type = "ollama-local" if provider_type == "ollama" else "openai-compatible"
    if connection and connection.get("type") == expected_type:
        return str(connection.get("model") or "")

    field = _CAPABILITY_FIELDS[capability]
    records = load_provider_records(osii_root)
    if records is not None:
        for provider in enabled_providers(osii_root):
            if str(provider.get("type") or "") != provider_type:
                continue
            configured = str(provider.get(field) or "").strip()
            if configured:
                return configured
            break

    if provider_type == "ollama":
        if capability == "embedder":
            return (
                os.getenv(
                    "OLLAMA_EMBEDDING_MODEL", DEFAULT_OLLAMA_EMBEDDING_MODEL
                ).strip()
                or DEFAULT_OLLAMA_EMBEDDING_MODEL
            )
        return (
            os.getenv(
                "OLLAMA_SYNTHESIS_MODEL",
                os.getenv("OLLAMA_CHAT_MODEL", DEFAULT_OLLAMA_CHAT_MODEL),
            ).strip()
            or DEFAULT_OLLAMA_CHAT_MODEL
        )
    if provider_type == "openai":
        if capability == "embedder":
            return os.getenv("OPENAI_EMBEDDING_MODEL", "").strip()
        return os.getenv("OPENAI_SYNTHESIS_MODEL", "").strip()
    return ""
