"""Small, dependency-free helpers shared by the OSII demonstrations."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import urllib.error
import urllib.request


@dataclass(frozen=True)
class DemoPaths:
    """Shared paths used by the later demonstration scripts."""

    workspace: Path
    source_root: Path
    osii_root: Path
    exports: Path

    def source_files(self) -> list[Path]:
        return sorted(path for path in self.source_root.rglob("*") if path.is_file())


def demo_paths() -> DemoPaths:
    """Return paths that work from a terminal, JupyterLab, or an IDE."""
    notebook_dir = Path(__file__).resolve().parent
    workspace = notebook_dir / "demo-workspace"
    return DemoPaths(
        workspace=workspace,
        source_root=notebook_dir / "documents",
        osii_root=workspace / ".osii",
        exports=workspace / "exports",
    )


def require_path(path: Path, instruction: str) -> None:
    if not path.exists():
        raise RuntimeError(f"Missing {path}. {instruction}")


def get_json(url: str, *, timeout: float = 2.0) -> dict | None:
    """Read a small JSON endpoint, returning None when a service is offline."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def processor_descriptor(base_url: str) -> dict | None:
    """Return a descriptor in the shape expected by OSII's commit adapters."""
    descriptor = get_json(f"{base_url.rstrip('/')}/v1/descriptor")
    if descriptor is None:
        return None
    return {**descriptor, "base_url": base_url.rstrip("/"), "remote": True}


def heading(text: str) -> None:
    print(f"\n{text}\n{'-' * len(text)}")
