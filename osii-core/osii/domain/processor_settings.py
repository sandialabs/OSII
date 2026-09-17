from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def processor_settings_path(osii_root: Path) -> Path:
    return osii_root / "state" / "processor_settings.json"


def load_processor_settings(osii_root: Path) -> dict[str, dict[str, Any]]:
    path = processor_settings_path(osii_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(name): dict(config)
        for name, config in payload.items()
        if isinstance(config, dict)
    }


def processor_settings(osii_root: Path, processor_name: str) -> dict[str, Any]:
    return dict(load_processor_settings(osii_root).get(processor_name, {}))


def save_processor_settings(
    osii_root: Path,
    processor_name: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    path = processor_settings_path(osii_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    settings = load_processor_settings(osii_root)
    settings[processor_name] = dict(config)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return dict(settings[processor_name])


def merged_processor_settings(
    osii_root: Path,
    processor_name: str | None,
    overrides: dict[str, Any] | None,
) -> dict[str, Any]:
    configured = processor_settings(osii_root, processor_name) if processor_name else {}
    return {**configured, **(overrides or {})}
