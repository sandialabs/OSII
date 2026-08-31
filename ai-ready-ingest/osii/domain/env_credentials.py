"""Resolve and persist local provider credentials without exposing their values."""

from __future__ import annotations

import os
from pathlib import Path
import re
import tempfile
import json


ENV_NAME = re.compile(r"[A-Z_][A-Z0-9_]*")


def configured_env_file() -> Path | None:
    value = os.getenv("OSII_ENV_FILE", "").strip()
    return Path(value).expanduser().resolve() if value else None


def local_config_writable() -> bool:
    return (
        os.getenv("OSII_ALLOW_LOCAL_CONFIG_WRITES", "").strip().lower()
        in {"1", "true", "yes", "on"}
        and configured_env_file() is not None
    )


def _decode(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            return str(json.loads(value))
        except json.JSONDecodeError:
            return value[1:-1]
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1]
    return value


def read_env_value(name: str) -> str:
    path = configured_env_file()
    if path is None or not path.exists():
        return ""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    result = ""
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == name:
            result = _decode(value)
    return result


def resolve_env_value(name: str, *aliases: str) -> tuple[str, str | None]:
    """Return ``(value, source)`` with process environment taking precedence."""
    names = tuple(item for item in (name, *aliases) if item)
    for candidate in names:
        value = os.getenv(candidate, "")
        if value:
            return value, "environment"
    for candidate in names:
        value = read_env_value(candidate)
        if value:
            return value, "repo_env"
    return "", None


def write_env_value(name: str, value: str | None) -> None:
    if not ENV_NAME.fullmatch(name):
        raise ValueError("Invalid environment-variable name")
    if not local_config_writable():
        raise PermissionError("Local .env updates are disabled for this deployment")
    if value is not None and ("\n" in value or "\r" in value):
        raise ValueError("Credentials cannot contain line breaks")

    target = configured_env_file()
    assert target is not None
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = target.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        existing = []

    replacement = None
    if value is not None:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        replacement = f'{name}="{escaped}"'
    output: list[str] = []
    found = False
    for line in existing:
        if "=" in line and line.split("=", 1)[0].strip() == name:
            if not found and replacement is not None:
                output.append(replacement)
            found = True
        else:
            output.append(line)
    if not found and replacement is not None:
        if output and output[-1] != "":
            output.append("")
        output.append(replacement)

    descriptor, temporary = tempfile.mkstemp(
        prefix=".osii-env-", dir=target.parent, text=True
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write("\n".join(output).rstrip() + ("\n" if output else ""))
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
