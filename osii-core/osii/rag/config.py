import os
from dataclasses import dataclass
from pathlib import Path

from osii.configuration import load_models_config, model_connection

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


def get_chat_settings(osii_root: Path) -> ChatSettings:
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    ollama_model = os.getenv("OLLAMA_CHAT_MODEL", "llama3.2:1b").strip() or "llama3.2:1b"
    openai_url = f"{os.getenv('OSII_MODEL_BRIDGE_URL', 'http://127.0.0.1:8095').rstrip('/')}/openai/v1"
    openai_model = os.getenv("OPENAI_CHAT_MODEL", os.getenv("OSII_CHAT_MODEL", "")).strip()
    openai_key = ""

    configuration = load_models_config(osii_root)
    chat_alias = str(configuration.get("defaults", {}).get("chat") or "")
    connection = model_connection(chat_alias, osii_root) if chat_alias else None
    if connection and "chat" in connection.get("capabilities", []):
        provider_type = str(connection.get("type") or "")
        if provider_type == "ollama-local":
            chain = ("ollama", "extractive")
            ollama_url = str(connection.get("base_url") or ollama_url).rstrip("/")
            ollama_model = str(connection.get("model") or ollama_model).strip() or ollama_model
        elif provider_type == "openai-compatible":
            chain = ("openai", "extractive")
            openai_model = str(connection.get("model") or openai_model).strip()
        else:
            chain = ("extractive",)
    else:
        chain = ("extractive",)

    # Explicit deployment overrides remain available for one release. Ordinary
    # Setup and launcher workflows use models.yml instead.
    configured_chain = os.getenv("CHAT_PROVIDER_CHAIN", "").strip()
    configured_primary = os.getenv("CHAT_PROVIDER", "").strip()
    if (configured_chain or configured_primary) and configuration.get("models"):
        chain = tuple(
            item.strip().lower()
            for item in (configured_chain or configured_primary).split(",")
            if item.strip()
        )

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
