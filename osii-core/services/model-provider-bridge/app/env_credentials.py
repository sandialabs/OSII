"""Read provider secrets from process environment or OSII's local env file."""

from __future__ import annotations

import os
from pathlib import Path
import json


def _file_value(name: str) -> str:
    configured = os.getenv("OSII_ENV_FILE", "").strip()
    if not configured:
        return ""
    try:
        lines = Path(configured).expanduser().read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    result = ""
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() != name:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            try:
                value = str(json.loads(value))
            except json.JSONDecodeError:
                value = value[1:-1]
        elif len(value) >= 2 and value[0] == value[-1] == "'":
            value = value[1:-1]
        result = value
    return result


def resolve_secret(*names: str) -> str:
    for name in names:
        if name and os.getenv(name, ""):
            return os.environ[name]
    for name in names:
        value = _file_value(name) if name else ""
        if value:
            return value
    return ""
