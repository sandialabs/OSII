import os
import json
from pathlib import Path
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    osii_backend_base_url: str
    chat_model: str
    chat_max_results: int
    chat_max_tokens: int
    preferred_search_mode: str
    fallback_search_mode: str
    chat_provider: str
    chat_provider_chain: tuple[str, ...]
    ollama_chat_model: str
    openai_chat_model: str
    ollama_base_url: str
    openai_compatible_base_url: str
    openai_compatible_api_key: str


def get_settings() -> Settings:
    primary = os.getenv("CHAT_PROVIDER", "ollama").strip().lower()
    chain = tuple(item.strip().lower() for item in os.getenv("CHAT_PROVIDER_CHAIN", primary).split(",") if item.strip())
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    ollama_model = os.getenv("OLLAMA_CHAT_MODEL", "llama3.2:1b").strip() or "llama3.2:1b"
    openai_url = os.getenv("OSII_CHAT_BASE_URL", os.getenv("OSII_MODEL_BASE_URL", "")).rstrip("/")
    openai_model = os.getenv("OSII_CHAT_MODEL", os.getenv("SHIRTY_CHAT_MODEL", "")).strip()
    openai_key = os.getenv("OSII_MODEL_API_KEY", "")
    root = Path(os.getenv("OSII_ROOT", "./osii-data/.osii"))
    provider_path = root / "state" / "model_providers.json"
    try:
        providers = json.loads(provider_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        providers = []
    enabled = sorted((item for item in providers if item.get("enabled")), key=lambda item: int(item.get("priority", 100)))
    if enabled:
        chain_items: list[str] = []
        for item in enabled:
            kind = str(item.get("type"))
            if kind == "ollama":
                chain_items.append("ollama")
                ollama_url = str(item.get("base_url") or ollama_url).rstrip("/")
                ollama_model = str(item.get("chat_model") or ollama_model)
            elif kind in {"openai", "shirty"}:
                chain_items.append("openai")
                openai_url = (
                    f"{os.getenv('OSII_MODEL_BRIDGE_URL', 'http://127.0.0.1:8095').rstrip('/')}/shirty/v1"
                    if kind == "shirty"
                    else str(item.get("base_url") or openai_url).rstrip("/")
                )
                openai_model = str(item.get("chat_model") or openai_model)
                env_name = str(item.get("credential_env") or ("SHIRTY_API_KEY" if kind == "shirty" else "OSII_MODEL_API_KEY"))
                openai_key = os.getenv(env_name, "")
        chain = tuple(dict.fromkeys([*chain_items, "extractive"]))
        primary = chain[0]
    elif provider_path.exists():
        # An explicit saved configuration with every provider disabled must
        # override the environment's first-run Ollama defaults.
        chain = ("extractive",)
        primary = "extractive"
    if "extractive" not in chain:
        chain = (*chain, "extractive")
    return Settings(
        osii_backend_base_url=os.getenv("OSII_BACKEND_BASE_URL", "http://localhost:8511").rstrip("/"),
        chat_model=os.getenv("CHAT_MODEL", "llama3.2:1b"),
        chat_max_results=int(os.getenv("CHAT_MAX_RESULTS", "8")),
        chat_max_tokens=int(os.getenv("CHAT_MAX_TOKENS", "900")),
        preferred_search_mode=os.getenv("PREFERRED_SEARCH_MODE", "hybrid"),
        fallback_search_mode=os.getenv("FALLBACK_SEARCH_MODE", "lexical"),
        chat_provider=primary,
        chat_provider_chain=chain,
        ollama_chat_model=ollama_model,
        openai_chat_model=openai_model,
        ollama_base_url=ollama_url,
        openai_compatible_base_url=openai_url,
        openai_compatible_api_key=openai_key,
    )
