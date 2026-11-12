"""Application configuration."""

from __future__ import annotations

import os
import platform

from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_demo_storage_dir() -> str:
    """Return the default demo storage directory.

    Returns
    -------
    str
        Default temporary storage directory for demo assets.
    """
    if platform.system().lower().startswith("win"):
        return r"C:\Temp\liteparse_demo"
    return "/tmp/liteparse_demo"


class Settings(BaseSettings):
    """Application settings."""

    enable_demo: bool = True
    demo_storage_dir: str = _default_demo_storage_dir()
    demo_max_file_size_mb: int = 50
    default_pdf_dpi: int = 200

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
os.makedirs(settings.demo_storage_dir, exist_ok=True)