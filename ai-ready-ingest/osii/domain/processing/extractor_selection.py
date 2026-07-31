from __future__ import annotations

import os
from pathlib import Path
import tomllib


def extractor_routes_path() -> Path:
    configured = os.getenv(
        "OSII_EXTRACTOR_ROUTES_PATH",
        "config/extractor_routes.toml",
    )
    return Path(configured).expanduser().resolve()


def load_extractor_routes(config_path: Path | None = None) -> list[dict]:
    path = config_path or extractor_routes_path()

    if not path.exists():
        return [{"name": "default-tika", "extractor": "tika", "extensions": ["*"]}]

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return data.get("routes", [])


def choose_extractor_for_path(path: Path, routes: list[dict]) -> str:
    suffix = path.suffix.lower()

    for route in routes:
        exts = route.get("extensions", [])
        if "*" in exts or suffix in [e.lower() for e in exts]:
            return route["extractor"]

    return "tika"
