#!/usr/bin/env python3
"""Create a Jupytext-style Python companion without changing the notebook."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def source_text(cell: dict[str, Any]) -> str:
    source = cell.get("source", "")
    return "".join(source) if isinstance(source, list) else str(source)


def render_markdown(source: str) -> str:
    lines = source.rstrip().splitlines() or [""]
    return "# %% [markdown]\n" + "\n".join("#" if not line else f"# {line}" for line in lines) + "\n\n"


def render_code(source: str) -> str:
    lines = source.rstrip().splitlines()
    safe = [f"# {line}" if line.lstrip().startswith(("%", "!")) else line for line in lines]
    candidate = "\n".join(safe)
    try:
        compile(candidate, "<notebook cell>", "exec")
    except SyntaxError:
        return render_markdown(source)
    return "# %%\n" + candidate + "\n\n"


def convert(notebook: Path, output: Path) -> None:
    payload = json.loads(notebook.read_text(encoding="utf-8"))
    cells = payload.get("cells")
    if not isinstance(cells, list):
        raise ValueError("not a valid Jupyter notebook: missing cells array")

    rendered = ["# Generated from a similarly named .ipynb notebook.\n\n"]
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        if cell.get("cell_type") == "markdown":
            rendered.append(render_markdown(source_text(cell)))
        elif cell.get("cell_type") == "code":
            rendered.append(render_code(source_text(cell)))
    output.write_text("".join(rendered), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert notebook files to marker-based Python files.")
    parser.add_argument("notebooks", nargs="+", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    for notebook in args.notebooks:
        if notebook.suffix != ".ipynb":
            parser.error(f"Expected an .ipynb file: {notebook}")
        output = (args.output_dir or notebook.parent) / f"{notebook.stem}.py"
        convert(notebook, output)
        print(output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
