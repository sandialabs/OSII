from __future__ import annotations

import os
from pathlib import Path
from pathlib import PureWindowsPath

from .pathing import path_within

MOUNTED_FOLDER_HELP = (
    "This folder is not connected to OSII's containers. Open OSII Launcher, "
    "choose it as the Document folder, test container access, save the library, "
    "and restart OSII. Then return to Intake. Your current selection is unchanged."
)

def resolve_intake_path(
    raw: str | None,
    source_root: Path,
    upload_root: Path,
    *,
    filesystem_mode: str = "local",
    host_root: str = "",
) -> Path:
    """Resolve only an explicitly requested location and report access failures."""
    cleaned = str(raw or "").strip().strip('"').strip("'")
    source_root = source_root.resolve()
    path = Path(cleaned).expanduser() if cleaned else source_root
    if filesystem_mode == "mounted" and cleaned and host_root:
        # The dashboard shows host paths; the API and worker use the mounted path.
        windows = bool(PureWindowsPath(host_root).drive)
        host = PureWindowsPath(host_root) if windows else Path(host_root)
        requested = PureWindowsPath(cleaned) if windows else Path(cleaned)
        if host.is_absolute() and requested.is_absolute():
            try:
                path = source_root.joinpath(*requested.relative_to(host).parts)
            except ValueError:
                if windows:
                    raise PermissionError(MOUNTED_FOLDER_HELP)
    if not path.is_absolute():
        path = source_root / path
    path = path.resolve()
    if filesystem_mode == "mounted" and not any(
        path_within(root, path) for root in (source_root, upload_root)
    ):
        raise PermissionError(MOUNTED_FOLDER_HELP)
    if not path.exists():
        raise FileNotFoundError(f"Folder or file not found: {cleaned or path}")
    return path


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
