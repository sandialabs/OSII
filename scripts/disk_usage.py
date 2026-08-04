#!/usr/bin/env python3
"""Read-only disk diagnostics for generated OSII development data."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    try:
        for entry in path.rglob("*"):
            try:
                if entry.is_file() and not entry.is_symlink():
                    total += entry.stat().st_size
            except OSError:
                continue
    except OSError:
        pass
    return total


def human(value: int) -> str:
    amount = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024 or unit == "TB":
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} TB"


def main() -> None:
    cache_home = Path(os.getenv("XDG_CACHE_HOME", Path.home() / ".cache"))
    candidates = [
        ("root Python environment", ROOT / ".venv"),
        ("notebook Python environment", ROOT / "osii-demo-notebooks" / ".venv"),
        ("dashboard node_modules", ROOT / "osii-dashboard" / "dashboard" / "node_modules"),
        ("staged OSII models", ROOT / "osii-data" / "models"),
        ("OSII derived data", ROOT / "osii-data" / ".osii"),
        ("Hugging Face cache", cache_home / "huggingface"),
        ("Ollama model store", Path.home() / ".ollama" / "models"),
    ]
    print("Generated and ignored disk usage (nothing is deleted):")
    for label, path in candidates:
        print(f"  {human(size(path)):>10}  {label}: {path}")
    podman = shutil.which("podman")
    if podman:
        print("\nPodman storage:")
        result = subprocess.run([podman, "system", "df"], text=True, capture_output=True, check=False)
        print((result.stdout or result.stderr).strip() or "  unavailable")


if __name__ == "__main__":
    main()
