"""Copyable failure evidence without request bodies or secret environment dumps."""
from __future__ import annotations
import errno
import importlib.metadata
import os
from pathlib import Path
import json
import platform
import re
import sys
import time
import traceback


def redact(value: str) -> str:
    for name, secret in os.environ.items():
        if re.search(r"KEY|TOKEN|SECRET|PASSWORD", name, re.I) and len(secret) >= 8:
            value = value.replace(secret, "[REDACTED]")
    secret_path = os.getenv("OSII_ENV_FILE", "")
    if secret_path:
        try:
            for line in Path(secret_path).read_text(encoding="utf-8").splitlines():
                name, separator, secret = line.partition("=")
                if separator and re.search(r"KEY|TOKEN|SECRET|PASSWORD", name, re.I):
                    secret = secret.strip()
                    if secret.startswith('"'):
                        try:
                            secret = json.loads(secret)
                        except ValueError:
                            secret = secret.strip('"')
                    else:
                        secret = secret.strip("'")
                    if isinstance(secret, str) and len(secret) >= 8:
                        value = value.replace(secret, "[REDACTED]")
        except OSError:
            pass
    value = re.sub(r"(?i)(Bearer\s+)[^\s\"']+", r"\1[REDACTED]", value)
    value = re.sub(r"(https?://)[^/\s:@]+:[^/\s@]+@", r"\1[REDACTED]@", value)
    return value


def environment() -> dict:
    packages = {}
    for name in ("osii", "fastapi", "uvicorn", "openai", "requests"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "not installed"
    return {"executable": sys.executable, "version": sys.version,
            "prefix": sys.prefix, "base_prefix": sys.base_prefix,
            "platform": platform.platform(), "packages": packages}


def failure(exc: Exception, *, processor: str, phase: str, endpoint: str | None = None, runtime: str = "Core worker") -> dict:
    return {"runtime": runtime, "processor": processor, "phase": phase, "endpoint": redact(endpoint or ""),
            "error_type": type(exc).__name__, "error": redact(str(exc)),
            "traceback": redact("".join(traceback.format_exception(type(exc), exc, exc.__traceback__))),
            "python": environment()}


def retry_file_access(operation, *, on_retry=None):
    """Three total attempts for transient reads only; no model/processor retries."""
    for attempt in range(3):
        try:
            return operation()
        except OSError as exc:
            transient = isinstance(exc, TimeoutError) or exc.errno in {
                errno.ETIMEDOUT, errno.ECONNRESET, errno.EAGAIN, errno.ESTALE,
            } or getattr(exc, "winerror", None) in {64, 121, 1231, 1232}
            if not transient or attempt == 2:
                raise
            if on_retry:
                on_retry(attempt + 1, exc)
            time.sleep((1, 3)[attempt])
