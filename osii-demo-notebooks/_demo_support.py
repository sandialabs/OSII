"""Small helpers shared by the flat, Jupytext-ready OSII demonstrations."""

from __future__ import annotations

from pathlib import Path


def demo_paths() -> tuple[Path, Path, Path]:
    """Return the notebook folder, source folder, and OSII store folder."""
    notebook_dir = Path.cwd()
    if not (notebook_dir / "requirements.txt").exists():
        notebook_dir = Path(__file__).resolve().parent
    workspace = notebook_dir / "demo-workspace"
    source_root = workspace / "source"
    osii_root = workspace / ".osii"
    source_root.mkdir(parents=True, exist_ok=True)
    return notebook_dir, source_root, osii_root


def require_file(path: Path, instruction: str) -> None:
    if not path.exists():
        raise RuntimeError(f"Missing {path}. {instruction}")
