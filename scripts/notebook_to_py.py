#!/usr/bin/env python3
"""Create review-friendly Python companions for Jupyter notebooks.

The converter uses only the Python standard library and keeps the original
notebook unchanged. Markdown becomes commented ``# %% [markdown]`` cells;
code becomes ``# %%`` cells. Notebook magics are commented so the result is
valid Python while retaining the original instruction.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def source_text(cell: dict[str, Any]) -> str:
    source = cell.get("source", "")
    return "".join(source) if isinstance(source, list) else str(source)


def markdown_cell(source: str) -> str:
    lines = source.rstrip().splitlines() or [""]
    return "# %% [markdown]\n" + "\n".join(
        "#" if not line else f"# {line}" for line in lines
    ) + "\n\n"


def code_cell(source: str) -> str:
    lines = source.rstrip().splitlines()
    safe_lines = [
        f"# {line}" if line.lstrip().startswith(("%", "!")) else line
        for line in lines
    ]
    candidate = "\n".join(safe_lines)
    try:
        compile(candidate, "<notebook cell>", "exec")
    except SyntaxError:
        # Some legacy notebooks contain prose in a code cell. Retain it, but
        # make the companion safe to run and parse as Python.
        return "# %% [markdown]\n" + "\n".join(
            "#" if not line else f"# {line}" for line in lines
        ) + "\n\n"
    return "# %%\n" + candidate + "\n\n"


def convert(notebook: Path, output: Path) -> None:
    payload = json.loads(notebook.read_text(encoding="utf-8"))
    cells = payload.get("cells")
    if not isinstance(cells, list):
        raise ValueError("not a valid Jupyter notebook: missing cells array")

    rendered = [
        "# This file is generated from the similarly named .ipynb notebook.\n"
        "# Edit this Python companion for normal code changes; preserve the notebook as an artifact.\n\n"
    ]
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        source = source_text(cell)
        if cell.get("cell_type") == "markdown":
            rendered.append(markdown_cell(source))
        elif cell.get("cell_type") == "code":
            rendered.append(code_cell(source))
    output.write_text("".join(rendered), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create .py companions for Jupyter notebooks.")
    parser.add_argument("notebooks", nargs="+", type=Path, help="Notebook files to convert.")
    parser.add_argument("--output-dir", type=Path, help="Directory for generated .py files; defaults to each notebook directory.")
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
