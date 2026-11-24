from __future__ import annotations

import mimetypes
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
IMAGE_OCR_EXTENSIONS = [".png", ".jpg", ".jpeg", ".tif", ".tiff"]


def has_default_reader(path: Path) -> bool:
    return path.suffix.lower() in (*NATIVE_EXTENSIONS, *IMAGE_OCR_EXTENSIONS)


def require_source_type(path: Path, capabilities: dict, extractor: str) -> None:
    """Apply declared source constraints without opening the file."""
    extensions = [value.strip().lower() for value in capabilities.get("file_extensions") or [] if value.strip()]
    if extensions:
        if "*" in extensions or path.suffix.lower() in extensions:
            return
        supported = extensions
        received = path.suffix or "(no extension)"
    else:
        media_types = [value.strip().lower() for value in capabilities.get("media_types") or [] if value.strip()]
        mime = mimetypes.guess_type(path.name)[0]
        if not media_types or "*/*" in media_types:
            return
        if mime and (mime.lower() in media_types or f"{mime.split('/')[0].lower()}/*" in media_types):
            return
        supported = media_types
        received = mime or "unknown media type"
    raise ValueError(f"Extractor '{extractor}' does not accept {received}; supported: {', '.join(supported)}")


def default_extractor_routes() -> list[dict]:
    return [
        {"name": "pdf-native-ocr", "extractor": "local.native-text",
         "fallbacks": ["local.tesseract-page-ocr"], "extensions": [".pdf"]},
        {"name": "native-supported", "extractor": "local.native-text", "fallbacks": [],
         "extensions": [suffix for suffix in NATIVE_EXTENSIONS if suffix != ".pdf"]},
        {"name": "images-ocr", "extractor": "local.tesseract-page-ocr", "fallbacks": [], "extensions": IMAGE_OCR_EXTENSIONS},
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
