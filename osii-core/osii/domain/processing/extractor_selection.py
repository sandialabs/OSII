from __future__ import annotations

import os
from pathlib import Path
import tomllib

from osii.configuration import load_tools_config, processors_path


NATIVE_EXTENSIONS = [
    ".cfg", ".conf", ".css", ".csv", ".docx", ".htm", ".html",
    ".ini", ".js", ".json", ".jsonl", ".log", ".md", ".pdf",
    ".pptx", ".py", ".rst", ".rtf", ".sql", ".toml", ".ts",
    ".tsv", ".txt", ".xlsx", ".xml", ".yaml", ".yml",
]


def default_extractor_routes() -> list[dict]:
    return [
        {"name": "native-supported", "extractor": "local.native-text", "fallbacks": [], "extensions": NATIVE_EXTENSIONS},
        {"name": "other-native", "extractor": "local.native-text", "fallbacks": [], "extensions": ["*"]},
    ]


def extractor_routes_path() -> Path:
    configured = os.getenv("OSII_EXTRACTOR_ROUTES_PATH", "").strip()
    return Path(configured).expanduser().resolve() if configured else processors_path()


def active_extractor_routes(routes: list[dict]) -> list[dict]:
    """Adapt archived Tika choices without rewriting saved configuration/history."""
    result = []
    for route in routes:
        chain = [route["extractor"], *route.get("fallbacks", [])]
        if not any(name in {"tika", "tika_catchall"} for name in chain):
            result.append(dict(route))
            continue
        remaining = list(dict.fromkeys(name for name in chain if name not in {"tika", "tika_catchall"})) or ["local.native-text"]
        result.append({**route, "extractor": remaining[0], "fallbacks": remaining[1:]})
    return result


def load_extractor_routes(config_path: Path | None = None) -> list[dict]:
    if config_path is None:
        routes = load_tools_config().get("routes", {}).get("extractor")
        if isinstance(routes, list):
            return active_extractor_routes(routes)
        configured = os.getenv("OSII_EXTRACTOR_ROUTES_PATH", "").strip()
        if not configured:
            return default_extractor_routes()
        path = Path(configured).expanduser().resolve()
    else:
        path = config_path

    if not path.exists():
        return default_extractor_routes()

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return active_extractor_routes(data.get("routes", []))


def choose_extractor_for_path(path: Path, routes: list[dict]) -> str:
    return extractor_chain_for_path(path, routes)[0]


def extractor_chain_for_path(path: Path, routes: list[dict]) -> list[str]:
    """Return the configured primary extractor followed by ordered fallbacks."""
    suffix = path.suffix.lower()

    for route in routes:
        exts = route.get("extensions", [])
        if "*" in exts or suffix in [e.lower() for e in exts]:
            chain = [str(route["extractor"])]
            chain.extend(str(item) for item in route.get("fallbacks", []) if item)
            return list(dict.fromkeys(chain))

    return ["local.native-text"]
