from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from osii.model_endpoints import ModelEndpoint, endpoint_from_environment


@dataclass(frozen=True)
class Settings:
    database_url: str
    source_root: Path
    model_url: str
    model_key: str = field(repr=False)
    extractor_url: str
    origins: tuple[str, ...]
    secure_cookies: bool
    ocr_url: str = ""
    embedding_endpoint: ModelEndpoint | None = None
    rerank_endpoint: ModelEndpoint | None = None
    remember_days: int = 14

    def endpoints(self) -> dict[str, ModelEndpoint]:
        return {"chat": ModelEndpoint(self.model_url, self.model_key),
                "embedding": self.embedding_endpoint or ModelEndpoint(self.model_url, self.model_key),
                "rerank": self.rerank_endpoint or ModelEndpoint()}

    def provider(self):
        from osii.model_provider import ModelProvider
        return ModelProvider(self.model_url, self.model_key, embedding_endpoint=self.embedding_endpoint)

    @classmethod
    def environment(cls) -> "Settings":
        database = os.environ.get("DATABASE_URL", "")
        if not database:
            raise ValueError("DATABASE_URL is required; OSII-server never falls back to files")
        chat = endpoint_from_environment("chat", default_url="https://openrouter.ai/api/v1")
        embedding = endpoint_from_environment("embedding", default_url="https://openrouter.ai/api/v1")
        rerank = endpoint_from_environment("rerank")
        source = Path(os.environ.get("OSII_SOURCE_DIR", "osii-data/source")).expanduser().resolve()
        origins = tuple(value.strip().rstrip("/") for value in os.environ.get(
            "OSII_ORIGINS", "http://localhost:5174,http://127.0.0.1:5174").split(",") if value.strip())
        secure = os.environ.get("OSII_INSECURE_LOCAL_HTTP", "false").lower() != "true"
        if not secure and any(not value.startswith(("http://localhost:", "http://127.0.0.1:")) for value in origins):
            raise ValueError("Insecure cookies are allowed only for explicit loopback development origins")
        remember_days = int(os.environ.get("OSII_REMEMBER_DAYS", "14"))
        if not 1 <= remember_days <= 30:
            raise ValueError("OSII_REMEMBER_DAYS must be between 1 and 30")
        return cls(database, source, chat.base_url, chat.api_key,
            os.environ.get("OSII_EXTRACTOR_URL", "http://127.0.0.1:8192"), origins, secure,
            os.environ.get("OSII_OCR_URL", ""), embedding, rerank, remember_days)
