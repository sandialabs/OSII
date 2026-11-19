#!/usr/bin/env python3
"""Small batch convenience wrapper around the Jupytext command-line tool."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent


def _run(*arguments: str) -> None:
    subprocess.run([sys.executable, "-m", "jupytext", *arguments], check=True)


def _python_sources() -> list[Path]:
    """Return demo scripts, identified by Jupytext percent cell markers."""
    return sorted(
        path
        for path in HERE.glob("*.py")
        if path != Path(__file__).resolve()
        and "# %%" in path.read_text(encoding="utf-8")
    )


def _notebook_sources() -> list[Path]:
    return sorted(HERE.glob("*.ipynb"))


def to_notebooks() -> int:
    sources = _python_sources()
    for source in sources:
        target = source.with_suffix(".ipynb")
        arguments = ["--to", "notebook"]
        if target.exists():
            arguments.insert(0, "--update")
        _run(*arguments, "--output", str(target), str(source))
        print(f"{source.name} -> {target.name}")
    return len(sources)


def to_python() -> int:
    sources = _notebook_sources()
    for source in sources:
        target = source.with_suffix(".py")
        _run("--to", "py:percent", "--output", str(target), str(source))
        print(f"{source.name} -> {target.name}")
    return len(sources)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert all Jupytext demo scripts and notebooks."
    )
    parser.add_argument(
        "direction",
        choices=("to-notebooks", "to-python"),
        help="Convert all marked .py demos or all .ipynb files.",
    )
    args = parser.parse_args()
    converted = to_notebooks() if args.direction == "to-notebooks" else to_python()
    print(f"Converted {converted} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
