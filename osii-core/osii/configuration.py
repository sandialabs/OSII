"""Installation-wide OSII model and processor configuration.

Canonical library content belongs in ``.osii``.  Model connections and service
registrations are workstation configuration instead, so they live in the
platform application-data directory and can be shared by several libraries.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any

import yaml


CONFIG_VERSION = 1
DEFAULT_PROFILE = "development"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MINILM = "all-minilm"
DEFAULT_LANGUAGE_MODEL = "llama3.2:1b"
_YAML_CACHE: dict[Path, dict[str, Any]] = {}
_YAML_ERRORS: dict[Path, str] = {}


def config_directory() -> Path:
    explicit = os.getenv("OSII_CONFIG_DIR", "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "org.osii.launcher" / "config"
    if os.name == "nt":
        root = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming"))
        return root / "org.osii.launcher" / "config"
    root = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "org.osii.launcher"


def models_path() -> Path:
    return config_directory() / "models.yml"


def tools_path() -> Path:
    return config_directory() / "tools.yml"


def secrets_path() -> Path:
    return config_directory() / "secrets.env"


def active_profile() -> str:
    return os.getenv("OSII_ACTIVE_PROFILE", DEFAULT_PROFILE).strip() or DEFAULT_PROFILE


def default_models_config() -> dict[str, Any]:
    ollama_url = os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL).rstrip("/")
    return {
        "version": CONFIG_VERSION,
        "models": {
            "base": {
                "type": "ollama-local",
                "base_url": ollama_url,
                "model": os.getenv("OLLAMA_CHAT_MODEL", DEFAULT_LANGUAGE_MODEL),
                "capabilities": ["chat", "synthesis"],
                "enabled": True,
            },
            "minilm": {
                "type": "ollama-local",
                "base_url": ollama_url,
                "model": os.getenv("OLLAMA_EMBEDDING_MODEL", DEFAULT_MINILM),
                "capabilities": ["embedding"],
                "enabled": True,
            },
        },
        "defaults": {"chat": "base", "synthesis": "base", "embedding": "minilm"},
    }


def default_tools_config() -> dict[str, Any]:
    return {
        "version": CONFIG_VERSION,
        "profiles": {
            DEFAULT_PROFILE: {
                "tools": {
                    "readable-llm-wiki": {
                        "enabled": True,
                        "processor_id": "toolbox.readable-wiki",
                        "display_name": "Readable LLM Wiki",
                        "kind": "enricher",
                        "model_requirements": {"chat": "required"},
                        "capabilities": {
                            "scope_types": ["object", "folder", "collection", "root"],
                            "output_kinds": ["wiki_markdown"],
                        },
                        "runtime": {"mode": "external", "endpoint": "http://127.0.0.1:8099"},
                        "model_access": {"mode": "gateway", "bindings": {"chat": "top"}},
                    },
                    "concept-entity-llm-wiki": {
                        "enabled": True,
                        "processor_id": "toolbox.concept-entity-wiki",
                        "display_name": "Concept and Entity LLM Wiki",
                        "kind": "enricher",
                        "model_requirements": {"chat": "required"},
                        "capabilities": {
                            "scope_types": ["object", "folder", "collection", "root"],
                            "output_kinds": ["wiki_markdown", "entity_list", "table"],
                        },
                        "runtime": {"mode": "external", "endpoint": "http://127.0.0.1:8100"},
                        "model_access": {"mode": "gateway", "bindings": {"chat": "mid"}},
                    },
                    "tesseract-opencv": {
                        "enabled": True,
                        "processor_id": "toolbox.tesseract-opencv",
                        "display_name": "Tesseract OCR with OpenCV regions",
                        "kind": "extractor",
                        "model_requirements": {},
                        "capabilities": {
                            "scope_types": ["object"],
                            "input_media_types": ["application/pdf", "image/*"],
                        },
                        "aliases": ["toolchest.tesseract-opencv"],
                        "runtime": {"mode": "external", "endpoint": "http://127.0.0.1:8081"},
                        "model_access": {"mode": "none"},
                    },
                }
            }
        },
    }


def _read_yaml(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return fallback
    except yaml.YAMLError as exc:
        location = ""
        if getattr(exc, "problem_mark", None) is not None:
            location = f" at line {exc.problem_mark.line + 1}, column {exc.problem_mark.column + 1}"
        _YAML_ERRORS[path] = f"Invalid YAML{location}: {getattr(exc, 'problem', str(exc))}"
        return _YAML_CACHE.get(path, fallback)
    except OSError as exc:
        _YAML_ERRORS[path] = str(exc)
        return _YAML_CACHE.get(path, fallback)
    if not isinstance(value, dict):
        _YAML_ERRORS[path] = "The YAML document must be a mapping."
        return _YAML_CACHE.get(path, fallback)
    _YAML_CACHE[path] = value
    _YAML_ERRORS.pop(path, None)
    return value


def _atomic_yaml(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            yaml.safe_dump(value, handle, sort_keys=False, allow_unicode=True)
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        _YAML_CACHE[path] = value
        _YAML_ERRORS.pop(path, None)
    finally:
        Path(temporary).unlink(missing_ok=True)


def save_models_config(value: dict[str, Any]) -> None:
    _atomic_yaml(models_path(), value)


def save_tools_config(value: dict[str, Any]) -> None:
    _atomic_yaml(tools_path(), value)


def _identifier(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return normalized or "model"


def _migrate_legacy_models(osii_root: Path) -> dict[str, Any] | None:
    legacy = osii_root / "state" / "model_providers.json"
    try:
        import json

        records = json.loads(legacy.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(records, list):
        return None
    result: dict[str, Any] = {
        "version": CONFIG_VERSION,
        "models": {},
        "defaults": {},
    }
    models = result["models"]
    for record in records:
        if not isinstance(record, dict) or not record.get("enabled", True):
            continue
        base_id = _identifier(str(record.get("id") or record.get("type") or "model"))
        provider_type = "ollama-local" if record.get("type") == "ollama" else "openai-compatible"
        common = {
            "type": provider_type,
            "base_url": str(record.get("base_url") or "").rstrip("/"),
            "api_key_env": str(record.get("credential_env") or "OPENAI_API_KEY"),
            "enabled": True,
        }
        embedding = str(record.get("embedding_model") or "").strip()
        if embedding:
            alias = "minilm" if provider_type == "ollama-local" and embedding == DEFAULT_MINILM else f"{base_id}-embedding"
            models[alias] = {**common, "model": embedding, "capabilities": ["embedding"]}
            result["defaults"]["embedding"] = alias
        language = str(record.get("chat_model") or record.get("synthesis_model") or "").strip()
        if language:
            alias = "base" if provider_type == "ollama-local" and language == DEFAULT_LANGUAGE_MODEL else f"{base_id}-language"
            models[alias] = {**common, "model": language, "capabilities": ["chat", "synthesis"]}
            result["defaults"].update({"chat": alias, "synthesis": alias})
    return result


def load_models_config(osii_root: Path | None = None) -> dict[str, Any]:
    path = models_path()
    if path.exists():
        return _read_yaml(path, default_models_config())
    migrated = _migrate_legacy_models(osii_root) if osii_root else None
    value = migrated or default_models_config()
    try:
        save_models_config(value)
    except OSError:
        pass
    return value


def _migrate_legacy_tools(osii_root: Path, value: dict[str, Any]) -> dict[str, Any]:
    legacy = osii_root / "state" / "processor_endpoints.json"
    try:
        import json

        records = json.loads(legacy.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return value
    tools = value.setdefault("profiles", {}).setdefault(active_profile(), {}).setdefault("tools", {})
    known_endpoints = {
        str(item.get("runtime", {}).get("endpoint"))
        for item in tools.values()
        if isinstance(item, dict)
    }
    for record in records if isinstance(records, list) else []:
        endpoint = str(record.get("base_url") or "").rstrip("/")
        if not endpoint or endpoint in known_endpoints:
            continue
        identifier = _identifier(str(record.get("id") or record.get("display_name") or "processor"))
        tools[identifier] = {
            "enabled": bool(record.get("enabled", True)),
            "processor_id": str(record.get("id") or identifier),
            "display_name": str(record.get("display_name") or identifier),
            "kind": str(record.get("kind") or "enricher"),
            "runtime": {"mode": "external", "endpoint": endpoint},
            "model_access": {"mode": "none"},
        }
    return value


def load_tools_config(osii_root: Path | None = None) -> dict[str, Any]:
    path = tools_path()
    if path.exists():
        return _read_yaml(path, default_tools_config())
    value = default_tools_config()
    if osii_root:
        value = _migrate_legacy_tools(osii_root, value)
    try:
        save_tools_config(value)
    except OSError:
        pass
    return value


def configured_models(osii_root: Path | None = None) -> dict[str, dict[str, Any]]:
    value = load_models_config(osii_root).get("models", {})
    return value if isinstance(value, dict) else {}


def model_connection(alias: str, osii_root: Path | None = None) -> dict[str, Any] | None:
    value = configured_models(osii_root).get(alias)
    return value if isinstance(value, dict) and value.get("enabled", True) else None


def configured_tools(osii_root: Path | None = None, profile: str | None = None) -> dict[str, dict[str, Any]]:
    profiles = load_tools_config(osii_root).get("profiles", {})
    selected = profiles.get(profile or active_profile(), {}) if isinstance(profiles, dict) else {}
    tools = selected.get("tools", {}) if isinstance(selected, dict) else {}
    return tools if isinstance(tools, dict) else {}


def tool_for_processor(processor_id: str, osii_root: Path | None = None) -> tuple[str, dict[str, Any]] | None:
    for tool_id, tool in configured_tools(osii_root).items():
        if not isinstance(tool, dict) or not tool.get("enabled", True):
            continue
        identities = {str(tool.get("processor_id") or ""), *map(str, tool.get("aliases") or [])}
        if processor_id in identities:
            return tool_id, tool
    return None


def configuration_status() -> dict[str, Any]:
    """Return paths and parse failures without exposing any secret values."""
    files = {"models": models_path(), "tools": tools_path(), "secrets": secrets_path()}
    return {
        "directory": str(config_directory()),
        "active_profile": active_profile(),
        "files": {name: str(path) for name, path in files.items()},
        "errors": {
            name: _YAML_ERRORS[path]
            for name, path in files.items()
            if path in _YAML_ERRORS
        },
        "generation": max(
            (path.stat().st_mtime_ns for path in files.values() if path.exists()),
            default=0,
        ),
    }
