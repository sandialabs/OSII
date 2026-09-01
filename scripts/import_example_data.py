#!/usr/bin/env python3
"""Install the small, public OSII demonstration corpus.

The scikit-learn loaders used here ship their data with the Python package, so
this script does not fetch datasets from the internet.  It serializes each
dataset as a ZIP archive in a temporary directory and then safely unpacks the
ordinary CSV and data-card files into OSII's configured source directory.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DESTINATION = REPOSITORY_ROOT / "osii-data" / "source"
PURCELL_SOURCE = (
    REPOSITORY_ROOT
    / "osii-demo-notebooks"
    / "demo-workspace"
    / "documents"
    / "purcell.pdf"
)


def configured_destination() -> Path:
    """Use the same source root as the normal launcher when it is configured."""
    configured = os.getenv("OSII_SOURCE_DIR", "").strip()
    env_file = REPOSITORY_ROOT / ".env"
    if not configured and env_file.is_file():
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line.startswith("OSII_SOURCE_DIR="):
                configured = line.split("=", 1)[1].strip().strip("'\"")
                break
    if not configured:
        return DEFAULT_DESTINATION
    destination = Path(configured)
    return destination if destination.is_absolute() else REPOSITORY_ROOT / destination


@dataclass(frozen=True)
class DatasetExport:
    slug: str
    display_name: str
    description: str
    feature_names: list[str]
    target_name: str
    target_names: list[str]
    rows: list[list[float]]
    targets: list[int]


def _csv_text(dataset: DatasetExport, row_indices: list[int]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow([*dataset.feature_names, dataset.target_name])
    for index in row_indices:
        values = dataset.rows[index]
        target = dataset.targets[index]
        writer.writerow([*values, target])
    return output.getvalue()


def _data_card(dataset: DatasetExport) -> str:
    return (
        f"# {dataset.display_name}\n\n"
        f"{dataset.description.strip()}\n\n"
        "This copy was exported from the dataset bundled with scikit-learn. "
        "Each CSV row is one observation; the final column is the numeric "
        "target class.\n"
    )


def build_dataset_archive(dataset: DatasetExport, archive_path: Path) -> None:
    """Create one deterministic, portable dataset archive."""
    metadata = {
        "name": dataset.display_name,
        "source": "scikit-learn bundled datasets",
        "row_count": len(dataset.rows),
        "feature_names": dataset.feature_names,
        "target_name": dataset.target_name,
        "target_names": dataset.target_names,
    }
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for target, target_name in enumerate(dataset.target_names):
            safe_target = "".join(
                character if character.isalnum() else "-"
                for character in target_name.lower()
            ).strip("-") or f"class-{target}"
            row_indices = [
                index for index, value in enumerate(dataset.targets) if value == target
            ]
            archive.writestr(
                f"{dataset.slug}/data/{safe_target}.csv",
                _csv_text(dataset, row_indices),
            )
        archive.writestr(f"{dataset.slug}/README.md", _data_card(dataset))
        archive.writestr(
            f"{dataset.slug}/dataset.json",
            json.dumps(metadata, indent=2) + "\n",
        )


def unpack_dataset_archive(archive_path: Path, destination: Path) -> list[Path]:
    """Extract an archive without permitting paths outside destination."""
    destination = destination.resolve()
    written: list[Path] = []
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            try:
                target.relative_to(destination)
            except ValueError as exc:
                raise ValueError(f"Unsafe archive member: {member.filename}") from exc
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            written.append(target)
    return written


def _load_datasets() -> list[DatasetExport]:
    try:
        from sklearn.datasets import load_iris, load_wine
    except ImportError as exc:
        raise RuntimeError(
            "scikit-learn is required. Use `make demo-data` or "
            "`.\\scripts\\osii.ps1 demo-data`; those commands provide it."
        ) from exc

    exports: list[DatasetExport] = []
    for slug, display_name, loader in (
        ("iris", "Iris flower measurements", load_iris),
        ("wine", "Wine cultivar measurements", load_wine),
    ):
        dataset = loader()
        exports.append(
            DatasetExport(
                slug=slug,
                display_name=display_name,
                description=str(dataset.DESCR).split("References", 1)[0],
                feature_names=[str(name) for name in dataset.feature_names],
                target_name="target_class",
                target_names=[str(name) for name in dataset.target_names],
                rows=[[float(value) for value in row] for row in dataset.data.tolist()],
                targets=[int(value) for value in dataset.target.tolist()],
            )
        )
    return exports


def install_example_data(destination: Path) -> list[Path]:
    destination = destination.resolve()
    documents_dir = destination / "example-documents"
    datasets_dir = destination / "example-datasets"
    documents_dir.mkdir(parents=True, exist_ok=True)
    datasets_dir.mkdir(parents=True, exist_ok=True)

    if not PURCELL_SOURCE.is_file():
        raise FileNotFoundError(f"Bundled PDF not found: {PURCELL_SOURCE}")
    purcell_target = documents_dir / "purcell.pdf"
    shutil.copy2(PURCELL_SOURCE, purcell_target)
    written = [purcell_target]

    with tempfile.TemporaryDirectory(prefix="osii-example-data-") as temporary:
        temporary_dir = Path(temporary)
        for dataset in _load_datasets():
            archive_path = temporary_dir / f"{dataset.slug}.zip"
            build_dataset_archive(dataset, archive_path)
            written.extend(unpack_dataset_archive(archive_path, datasets_dir))
    return written


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy OSII's PDF and unpack two bundled scikit-learn datasets."
    )
    parser.add_argument(
        "--destination",
        type=Path,
        default=None,
        help="OSII source directory (default: OSII_SOURCE_DIR or osii-data/source).",
    )
    args = parser.parse_args()

    destination = args.destination or configured_destination()
    written = install_example_data(destination)
    print(f"Installed {len(written)} example file(s) under {destination.resolve()}:")
    for path in written:
        print(f"- {path.relative_to(destination.resolve())}")
    print("\nStart OSII with `make dev-datasets` and open Intake.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
