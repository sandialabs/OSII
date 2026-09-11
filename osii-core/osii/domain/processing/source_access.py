from __future__ import annotations

import os
from pathlib import Path


def _windows_drive_is_remote(path: Path) -> bool:
    if os.name != "nt" or not path.anchor:
        return False
    try:
        import ctypes

        drive_type = ctypes.windll.kernel32.GetDriveTypeW(str(path.anchor))
    except (AttributeError, OSError):
        return False
    return drive_type == 4  # DRIVE_REMOTE


def source_kind(path: Path, configured_kind: str | None = None) -> str:
    configured = (configured_kind or "auto").strip().lower()
    if configured in {"local", "shared"}:
        return configured

    raw = str(path)
    if raw.startswith("\\\\") or raw.startswith("//") or _windows_drive_is_remote(path):
        return "shared"
    return "local"


def source_access_summary(
    source_root: Path,
    osii_root: Path,
    *,
    configured_kind: str | None = None,
) -> dict:
    kind = source_kind(source_root, configured_kind)
    available = source_root.exists() and source_root.is_dir()
    readable = False
    detail: str | None = None

    if available:
        try:
            with os.scandir(source_root) as entries:
                next(entries, None)
            readable = True
        except OSError as exc:
            detail = str(exc)
    else:
        detail = "The configured documents folder is not currently available."

    source_writable = readable and os.access(source_root, os.W_OK)
    osii_writable = osii_root.exists() and osii_root.is_dir() and os.access(osii_root, os.W_OK)
    if not readable:
        mode = "unavailable"
    elif source_writable:
        mode = "read_write"
    else:
        mode = "read_only"

    if readable and not osii_writable:
        detail = "The documents are readable, but OSII's local artifact folder is not writable."
    elif readable and kind == "shared":
        detail = (
            "The shared documents are connected. OSII reads originals in place and writes "
            "derived artifacts to the separate OSII data folder."
        )

    return {
        "kind": kind,
        "source_root": str(source_root),
        "osii_root": str(osii_root),
        "available": available and readable,
        "readable": readable,
        "source_mode": mode,
        "osii_writable": osii_writable,
        "ready_for_intake": readable and osii_writable,
        "detail": detail,
    }
