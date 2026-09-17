"""Per-profile, non-secret model, processor, and routing configuration."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import tempfile
import tomllib
from typing import Any

import tomli_w
import yaml


CONFIG_VERSION = 1
DEFAULT_PROFILE = "development"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MINILM = "all-minilm"
DEFAULT_LANGUAGE_MODEL = "llama3.2:1b"
_CONFIG_CACHE: dict[Path, dict[str, Any]] = {}
_CONFIG_ERRORS: dict[Path, str] = {}


def config_directory() -> Path:
    explicit = os.getenv("OSII_CONFIG_DIR", "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "org.osii.launcher" / "profiles" / "development" / "deployment"
    if os.name == "nt":
        root = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming"))
        return root / "org.osii.launcher" / "profiles" / "development" / "deployment"
    root = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / "org.osii.launcher" / "profiles" / "development" / "deployment"


def models_path() -> Path:
    return config_directory() / "models.toml"


def tools_path() -> Path:
    return config_directory() / "tools.toml"


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


def builtin_tools_config() -> dict[str, Any]:
    return {
        "version": CONFIG_VERSION,
        "tools": {
            "readable-llm-wiki": {
                "enabled": True,
                "processor_id": "toolbox.readable-wiki",
                "display_name": "Readable LLM Wiki",
                "kind": "enricher",
                "runtime": {"mode": "external", "endpoint": "http://127.0.0.1:8099"},
                "model_access": {"mode": "gateway", "bindings": {"chat": "top"}},
            },
            "concept-entity-llm-wiki": {
                "enabled": True,
                "processor_id": "toolbox.concept-entity-wiki",
                "display_name": "Concept and Entity LLM Wiki",
                "kind": "enricher",
                "runtime": {"mode": "external", "endpoint": "http://127.0.0.1:8100"},
                "model_access": {"mode": "gateway", "bindings": {"chat": "mid"}},
            },
            "tesseract-opencv": {
                "enabled": True,
                "processor_id": "toolbox.tesseract-opencv",
                "display_name": "Tesseract OCR with OpenCV regions",
                "kind": "extractor",
                "aliases": ["toolchest.tesseract-opencv"],
                "runtime": {"mode": "external", "endpoint": "http://127.0.0.1:8081"},
                "model_access": {"mode": "none"},
            },
        },
    }


def default_tools_config() -> dict[str, Any]:
    """Only user changes are persisted; built-in optional registrations live in code."""
    return {"version": CONFIG_VERSION}


def _read_toml(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return fallback
    except tomllib.TOMLDecodeError as exc:
        line = getattr(exc, "lineno", None)
        column = getattr(exc, "colno", None)
        location = f" at line {line}, column {column}" if line and column else ""
        _CONFIG_ERRORS[path] = f"Invalid TOML{location}: {exc}"
        return _CONFIG_CACHE.get(path, fallback)
    except OSError as exc:
        _CONFIG_ERRORS[path] = str(exc)
        return _CONFIG_CACHE.get(path, fallback)
    if not isinstance(value, dict):
        _CONFIG_ERRORS[path] = "The TOML document must be a table."
        return _CONFIG_CACHE.get(path, fallback)
    expected = ("models", "defaults") if path == models_path() else ("tools", "routes", "processor_settings")
    invalid = next((name for name in expected if name in value and not isinstance(value[name], dict)), None)
    if invalid:
        _CONFIG_ERRORS[path] = f"The [{invalid}] section must be a TOML table."
        return _CONFIG_CACHE.get(path, fallback)
    _CONFIG_CACHE[path] = value
    _CONFIG_ERRORS.pop(path, None)
    return value


def _atomic_toml(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(tomli_w.dumps(value))
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        _CONFIG_CACHE[path] = value
        _CONFIG_ERRORS.pop(path, None)
    finally:
        Path(temporary).unlink(missing_ok=True)


def save_models_config(value: dict[str, Any]) -> None:
    _atomic_toml(models_path(), value)


def save_tools_config(value: dict[str, Any]) -> None:
    _atomic_toml(tools_path(), value)


def _read_legacy_yaml(name: str) -> dict[str, Any] | None:
    directories = [config_directory()]
    previous = os.getenv("OSII_LEGACY_CONFIG_DIR", "").strip()
    if previous:
        directories.append(Path(previous).expanduser())
    for directory in directories:
        path = directory / name
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if isinstance(value, dict):
            return _drop_nulls(value)
    return None


def _drop_nulls(value: Any) -> Any:
    """TOML has no null value; omit unset fields from older YAML profiles."""
    if isinstance(value, dict):
        return {key: _drop_nulls(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_drop_nulls(item) for item in value if item is not None]
    return value


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
        return _read_toml(path, default_models_config())
    migrated = _read_legacy_yaml("models.yml")
    if migrated is None and osii_root:
        migrated = _migrate_legacy_models(osii_root)
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
    tools = value.setdefault("tools", {})
    known_endpoints = {
        str(item.get("runtime", {}).get("endpoint"))
        for item in [*builtin_tools_config()["tools"].values(), *tools.values()]
        if isinstance(item, dict)
    }
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict):
            continue
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


def _migrate_core_routes(value: dict[str, Any]) -> dict[str, Any]:
    """Copy previously edited route files once; shipped native defaults stay in code."""
    core_config = Path(__file__).resolve().parents[1] / "config"
    candidates = {
        "extractor": Path(os.getenv("OSII_EXTRACTOR_ROUTES_PATH", "").strip())
        if os.getenv("OSII_EXTRACTOR_ROUTES_PATH", "").strip()
        else core_config / "extractor_routes.toml",
        "object_synthesis": core_config / "object_synth_routes.toml",
        "folder_synthesis": core_config / "folder_synth_routes.toml",
    }
    for kind, path in candidates.items():
        if kind in value.get("routes", {}):
            continue
        try:
            routes = tomllib.loads(path.read_text(encoding="utf-8")).get("routes", [])
        except (OSError, tomllib.TOMLDecodeError):
            continue
        if kind == "extractor" and path == core_config / "extractor_routes.toml" and routes == [
            {"name": "pdf-local-tika", "extractor": "tika", "fallbacks": ["local.native-text"], "extensions": [".pdf"]},
            {"name": "office-local-tika", "extractor": "tika", "fallbacks": ["local.native-text"], "extensions": [".docx", ".doc"]},
            {"name": "tika-catchall", "extractor": "tika", "fallbacks": ["local.native-text"], "extensions": ["*"]},
        ]:
            continue
        if isinstance(routes, list) and routes:
            value.setdefault("routes", {})[kind] = routes
    return value


def _migrate_legacy_settings(osii_root: Path, value: dict[str, Any]) -> dict[str, Any]:
    path = osii_root / "state" / "processor_settings.json"
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return value
    if isinstance(settings, dict):
        for name, overrides in settings.items():
            if isinstance(overrides, dict) and overrides:
                try:
                    tomli_w.dumps({"settings": overrides})
                except (TypeError, ValueError):
                    continue  # Old JSON remains readable for non-TOML values such as null.
                value.setdefault("processor_settings", {}).setdefault(name, overrides)
    return value


def load_tools_config(osii_root: Path | None = None) -> dict[str, Any]:
    path = tools_path()
    if path.exists():
        value = _read_toml(path, default_tools_config())
        if path in _CONFIG_ERRORS:
            return value
        if osii_root and not value.get("legacy_state_imported") and any(
            (osii_root / "state" / name).exists()
            for name in ("processor_endpoints.json", "processor_settings.json")
        ):
            value = _migrate_legacy_settings(osii_root, _migrate_legacy_tools(osii_root, value))
            value["legacy_state_imported"] = True
            try:
                save_tools_config(value)
            except OSError:
                pass
        return value
    value = _read_legacy_yaml("tools.yml") or default_tools_config()
    if "profiles" in value:
        profiles = value.pop("profiles")
        selected = profiles.get(active_profile(), profiles.get(DEFAULT_PROFILE, {})) if isinstance(profiles, dict) else {}
        value["tools"] = selected.get("tools", {}) if isinstance(selected, dict) else {}
    value = _migrate_core_routes(value)
    if osii_root:
        value = _migrate_legacy_tools(osii_root, value)
        value = _migrate_legacy_settings(osii_root, value)
        if any((osii_root / "state" / name).exists() for name in ("processor_endpoints.json", "processor_settings.json")):
            value["legacy_state_imported"] = True
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
    overrides = load_tools_config(osii_root).get("tools", {})
    tools = dict(builtin_tools_config()["tools"]) if (profile or active_profile()) == DEFAULT_PROFILE else {}
    if isinstance(overrides, dict):
        tools.update(overrides)
    return tools


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
            name: _CONFIG_ERRORS[path]
            for name, path in files.items()
            if path in _CONFIG_ERRORS
        },
        "generation": max(
            (path.stat().st_mtime_ns for path in files.values() if path.exists()),
            default=0,
        ),
    }
