#!/usr/bin/env python3
"""Convert Jupytext-marked Python demonstrations to Jupyter notebooks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert marker-based Python files to .ipynb notebooks.")
    parser.add_argument("sources", nargs="+", type=Path, help="Python files with Jupytext cell markers.")
    parser.add_argument("--output-dir", type=Path, help="Directory for generated notebooks.")
    args = parser.parse_args()

    try:
        import jupytext
    except ImportError as error:
        raise RuntimeError("Install this folder's requirements first: python -m pip install -r requirements.txt") from error

    for source in args.sources:
        if source.suffix != ".py":
            parser.error(f"Expected a .py file: {source}")
        output = (args.output_dir or source.parent) / f"{source.stem}.ipynb"
        notebook = jupytext.read(source)
        jupytext.write(notebook, output, fmt="ipynb")
        print(output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
