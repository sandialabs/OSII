#!/usr/bin/env python3
"""Convert the canonical OSII demonstrations between Python and notebooks.

The reviewable ``.py`` files use Jupytext percent markers. This utility is the
only normal reason to parse or write notebook JSON in this directory.
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
CANONICAL_STEMS = (
    "00_Setup_a_demo_workspace",
    "01_Create_an_OSII_store",
    "02_Extract_documents_locally",
    "03_Create_local_text_previews",
    "04_Browse_objects_and_create_a_collection",
    "05_Build_and_search_a_lexical_index",
    "06_Build_local_embeddings",
    "07_Create_a_standard_enrichment",
    "08_Connect_an_optional_model_or_processor",
)


def _require_jupytext() -> None:
    if importlib.util.find_spec("jupytext") is None:
        raise RuntimeError(
            "Jupytext is not installed. Run: python -m pip install -r requirements.txt"
        )


def _run_jupytext(*arguments: str) -> None:
    """Use Jupytext's public CLI rather than duplicating conversion logic."""
    _require_jupytext()
    subprocess.run(
        [sys.executable, "-m", "jupytext", *arguments],
        check=True,
    )


def _resolve_source(value: str, suffix: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = HERE / path
    if path.suffix == "":
        path = path.with_suffix(suffix)
    if path.suffix != suffix:
        raise ValueError(f"Expected a {suffix} source: {value}")
    return path.resolve()


def _sources(command: str, requested: list[str]) -> list[Path]:
    suffix = ".py" if command == "to-notebooks" else ".ipynb"
    if requested:
        sources = [_resolve_source(value, suffix) for value in requested]
    else:
        sources = [(HERE / stem).with_suffix(suffix) for stem in CANONICAL_STEMS]
        sources = [path for path in sources if path.exists()]
    missing = [path for path in sources if not path.is_file()]
    if missing:
        raise ValueError("Missing source file(s): " + ", ".join(str(path) for path in missing))
    return sources


def convert(command: str, sources: list[Path], *, output_dir: Path, force: bool) -> int:
    target_suffix = ".ipynb" if command == "to-notebooks" else ".py"
    converted = 0

    output_dir.mkdir(parents=True, exist_ok=True)
    for source in sources:
        target = output_dir / f"{source.stem}{target_suffix}"
        if command == "to-python" and target.exists() and not force:
            print(f"SKIP {target.name}: target exists (rerun with --force to replace it)")
            continue

        if command == "to-notebooks":
            arguments = ["--to", "notebook", "--output", str(target), str(source)]
            action = "created"
            if target.exists() and not force:
                # This is the canonical Jupytext update operation: replace
                # inputs while preserving notebook outputs and metadata.
                arguments.insert(0, "--update")
                action = "updated inputs; preserved outputs and metadata"
            elif target.exists():
                action = "replaced (outputs removed)"
        else:
            arguments = ["--to", "py:percent", "--output", str(target), str(source)]
            action = "created" if not target.exists() else "replaced"

        _run_jupytext(*arguments)
        print(f"{source.name} -> {target} [{action}]")
        converted += 1
    return converted


def test_roundtrip(sources: list[Path]) -> int:
    for source in sources:
        _run_jupytext("--to", "py:percent", "--test", str(source))
        print(f"PASS {source.name}")
    return len(sources)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert all canonical OSII demos, or selected files, with Jupytext."
    )
    parser.add_argument(
        "command",
        choices=("to-notebooks", "to-python", "test-roundtrip", "list"),
    )
    parser.add_argument("files", nargs="*", help="Optional filenames or stems; defaults to all canonical demos.")
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Replace existing targets. Without this flag, notebook updates preserve "
            "outputs/metadata and Python targets are protected."
        ),
    )
    parser.add_argument("--output-dir", type=Path, help="Target directory; defaults to this directory.")
    args = parser.parse_args()

    if args.command == "list":
        for stem in CANONICAL_STEMS:
            print(stem)
        return 0

    output_dir = (args.output_dir or HERE).resolve()
    sources = _sources(args.command, args.files)
    if not sources:
        expected = ".py" if args.command == "to-notebooks" else ".ipynb"
        print(f"No canonical {expected} sources exist yet.")
        return 0

    if args.command == "test-roundtrip":
        converted = test_roundtrip(sources)
        print(f"Tested {converted} file(s).")
        return 0

    converted = convert(args.command, sources, output_dir=output_dir, force=args.force)
    print(f"Converted {converted} file(s).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
