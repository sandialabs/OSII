from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from osii.configuration import load_tools_config, save_tools_config


def processor_settings_path(osii_root: Path) -> Path:
    return osii_root / "state" / "processor_settings.json"


def load_processor_settings(osii_root: Path) -> dict[str, dict[str, Any]]:
    configured = load_tools_config(osii_root).get("processor_settings", {})
    current = (
        {
            str(name): dict(settings)
            for name, settings in configured.items()
            if isinstance(settings, dict)
        }
        if isinstance(configured, dict) else {}
    )
    # One-release fallback for records containing JSON null, which TOML cannot encode.
    path = processor_settings_path(osii_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return current
    if not isinstance(payload, dict):
        return current
    for name, config in payload.items():
        if isinstance(config, dict):
            current.setdefault(str(name), dict(config))
    return current


def processor_settings(osii_root: Path, processor_name: str) -> dict[str, Any]:
    return dict(load_processor_settings(osii_root).get(processor_name, {}))


def save_processor_settings(
    osii_root: Path,
    processor_name: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    configuration = load_tools_config(osii_root)
    configuration.setdefault("processor_settings", {})[processor_name] = dict(config)
    save_tools_config(configuration)
    return dict(config)


def merged_processor_settings(
    osii_root: Path,
    processor_name: str | None,
    overrides: dict[str, Any] | None,
) -> dict[str, Any]:
    configured = processor_settings(osii_root, processor_name) if processor_name else {}
    return {**configured, **(overrides or {})}
