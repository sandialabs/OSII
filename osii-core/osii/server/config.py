from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    source_root: Path
    model_url: str
    model_key: str
    extractor_url: str
    origins: tuple[str, ...]
    secure_cookies: bool
    ocr_url: str = ""

    @classmethod
    def environment(cls) -> "Settings":
        database = os.environ.get("DATABASE_URL", "")
        if not database:
            raise ValueError("DATABASE_URL is required; OSII-server never falls back to files")
        key = os.environ.get("OSII_MODEL_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
        path = os.environ.get("OSII_MODEL_API_KEY_FILE", "")
        if path:
            key = Path(path).read_text().strip()
        source = Path(os.environ.get("OSII_SOURCE_DIR", "osii-data/source")).expanduser().resolve()
        origins = tuple(value.strip().rstrip("/") for value in os.environ.get(
            "OSII_ORIGINS", "http://localhost:5174,http://127.0.0.1:5174").split(",") if value.strip())
        secure = os.environ.get("OSII_INSECURE_LOCAL_HTTP", "false").lower() != "true"
        if not secure and any(not value.startswith(("http://localhost:", "http://127.0.0.1:")) for value in origins):
            raise ValueError("Insecure cookies are allowed only for explicit loopback development origins")
        return cls(database, source, os.environ.get("OPENAI_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/"),
            key, os.environ.get("OSII_EXTRACTOR_URL", "http://127.0.0.1:8192"), origins, secure,
            os.environ.get("OSII_OCR_URL", ""))
