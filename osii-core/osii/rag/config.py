import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any



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
    chain = tuple(
        item.strip().lower()
        for item in configured_chain.split(",")
        if item.strip()
    )
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    ollama_model = os.getenv("OLLAMA_CHAT_MODEL", "llama3.2:1b").strip() or "llama3.2:1b"
    openai_url = f"{os.getenv('OSII_MODEL_BRIDGE_URL', 'http://127.0.0.1:8095').rstrip('/')}/openai/v1"
    openai_model = os.getenv("OPENAI_CHAT_MODEL", os.getenv("OSII_CHAT_MODEL", "")).strip()
    openai_key = ""

    records = _provider_records(osii_root)
    if records is not None:
        enabled = sorted(
            (item for item in records if item.get("enabled")),
            key=lambda item: int(item.get("priority", 100)),
        )
        if not enabled:
            chain = ("extractive",)
        else:
            configured: list[str] = []
            for item in enabled:
                kind = str(item.get("type") or "").strip().lower()
                if kind == "ollama":
                    configured.append("ollama")
                    ollama_url = str(item.get("base_url") or ollama_url).rstrip("/")
                    ollama_model = (
                        str(item.get("chat_model") or ollama_model).strip()
                        or ollama_model
                    )
                elif kind in {"openai", "openai_compatible"}:
                    configured.append("openai")
                    openai_model = str(item.get("chat_model") or openai_model).strip()
            chain = tuple(dict.fromkeys([*configured, "extractive"]))

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
