import os
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
    ollama_base_url: str
    openai_compatible_base_url: str
    openai_compatible_api_key: str


def get_settings() -> Settings:
    return Settings(
        osii_backend_base_url=os.getenv("OSII_BACKEND_BASE_URL", "http://localhost:8511").rstrip("/"),
        chat_model=os.getenv("CHAT_MODEL", "openai/gpt-oss-120b"),
        chat_max_results=int(os.getenv("CHAT_MAX_RESULTS", "8")),
        chat_max_tokens=int(os.getenv("CHAT_MAX_TOKENS", "900")),
        preferred_search_mode=os.getenv("PREFERRED_SEARCH_MODE", "hybrid"),
        fallback_search_mode=os.getenv("FALLBACK_SEARCH_MODE", "lexical"),
        chat_provider=os.getenv("CHAT_PROVIDER", "extractive").strip().lower(),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/"),
        openai_compatible_base_url=os.getenv("OSII_CHAT_BASE_URL", os.getenv("OSII_MODEL_BASE_URL", "")).rstrip("/"),
        openai_compatible_api_key=os.getenv("OSII_MODEL_API_KEY", ""),
    )
