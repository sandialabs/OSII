#!/usr/bin/env python3
"""Export OSII components as transfer-ready directory trees.

The export never modifies this repository. It deliberately does not initialize
Git repositories or rewrite dependency metadata: the receiving corporate
environment can apply its own package registry and repository conventions.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ExportEntry:
    source: str
    destination: str


COMPONENTS: dict[str, tuple[ExportEntry, ...]] = {
    "backend": (
        ExportEntry("ai-ready-ingest", "."),
        ExportEntry("docs/reference/api", "docs/reference/api"),
        ExportEntry("docs/reference/processor-api", "docs/reference/processor-api"),
    ),
    "frontend": (
        ExportEntry("osii-dashboard/dashboard", "."),
        ExportEntry("docs/reference/api", "docs/reference/api"),
    ),
    "mcp": (
        ExportEntry("ai-ready-mcp", "."),
        ExportEntry("docs/reference/api", "docs/reference/api"),
        ExportEntry("docs/reference/processor-api", "docs/reference/processor-api"),
    ),
    "chat": (
        ExportEntry("ai-ready-rag-chat", "."),
        ExportEntry("docs/reference/api", "docs/reference/api"),
    ),
    "tools": (
        ExportEntry("ai-ready-tool-shelf", "tools"),
        ExportEntry("packages/osii-processor-sdk", "packages/osii-processor-sdk"),
        ExportEntry("services/table-pdf-enricher", "services/table-pdf-enricher"),
        ExportEntry("services/local-extractor", "services/local-extractor"),
        ExportEntry("services/local-synthesizer", "services/local-synthesizer"),
        ExportEntry("services/local-embedder", "services/local-embedder"),
        ExportEntry("services/local-enricher", "services/local-enricher"),
        ExportEntry("docs/extending", "docs/extending"),
        ExportEntry("docs/reference/processor-api", "docs/reference/processor-api"),
    ),
    "notebooks": (
        ExportEntry("osii-demo-notebooks", "."),
        ExportEntry("docs/tutorials", "docs/tutorials"),
    ),
    "local-extractor": (
        ExportEntry("services/local-extractor", "."),
        ExportEntry("packages/osii-processor-sdk", "packages/osii-processor-sdk"),
        ExportEntry("docs/reference/processor-api", "docs/reference/processor-api"),
    ),
    "local-synthesizer": (
        ExportEntry("services/local-synthesizer", "."),
        ExportEntry("packages/osii-processor-sdk", "packages/osii-processor-sdk"),
        ExportEntry("docs/reference/processor-api", "docs/reference/processor-api"),
    ),
    "local-embedder": (
        ExportEntry("services/local-embedder", "."),
        ExportEntry("packages/osii-processor-sdk", "packages/osii-processor-sdk"),
        ExportEntry("docs/reference/processor-api", "docs/reference/processor-api"),
    ),
    "local-enricher": (
        ExportEntry("services/local-enricher", "."),
        ExportEntry("packages/osii-processor-sdk", "packages/osii-processor-sdk"),
        ExportEntry("docs/reference/processor-api", "docs/reference/processor-api"),
    ),
}

IGNORED_NAMES = {
    ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv",
    "__pycache__", "node_modules", "dist", "build", ".vite",
    "data_volume", "osii-data",
}


def ignore_generated(_: str, names: list[str]) -> set[str]:
    return {name for name in names if name in IGNORED_NAMES or name.endswith(".pyc")}


def parse_components(raw: str) -> list[str]:
    selected = [part.strip().lower() for part in raw.split(",") if part.strip()]
    unknown = sorted(set(selected) - set(COMPONENTS))
    if unknown:
        raise ValueError(f"Unknown component(s): {', '.join(unknown)}")
    return selected or list(COMPONENTS)


def copy_entry(component_root: Path, entry: ExportEntry) -> None:
    source = REPOSITORY_ROOT / entry.source
    destination = component_root / entry.destination
    if not source.exists():
        raise FileNotFoundError(f"Export source is missing: {source}")
    if entry.destination == ".":
        destination.mkdir(parents=True, exist_ok=True)
        for child in source.iterdir():
            if child.name in IGNORED_NAMES or child.name.endswith(".pyc"):
                continue
            target = destination / child.name
            if child.is_dir():
                shutil.copytree(child, target, ignore=ignore_generated, dirs_exist_ok=True)
            else:
                shutil.copy2(child, target)
        return
    shutil.copytree(source, destination, ignore=ignore_generated, dirs_exist_ok=True)


def write_manifest(output: Path, selected: list[str]) -> None:
    manifest = {
        "source_repository": "osii",
        "components": selected,
        "notes": {
            "backend": "Publish the osii Python package to the corporate package registry before exporting MCP consumers.",
            "frontend": "Configure its API endpoint for the deployed OSII backend.",
            "tools": "Processor services use the shared osii-processor-sdk contract package.",
        },
    }
    (output / "EXPORT_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def adapt_container_files(component: str, component_root: Path) -> None:
    """Make Dockerfiles use the exported directory as their build context."""
    dockerfile = component_root / "Dockerfile"
    if component == "backend" and dockerfile.exists():
        content = dockerfile.read_text(encoding="utf-8")
        content = content.replace("COPY ai-ready-ingest/pyproject.toml ai-ready-ingest/README.md ./", "COPY pyproject.toml README.md ./")
        content = content.replace("COPY ai-ready-ingest/osii ./osii", "COPY osii ./osii")
        content = content.replace("COPY ai-ready-ingest/config ./config", "COPY config ./config")
        dockerfile.write_text(content, encoding="utf-8")
    if component == "mcp" and dockerfile.exists():
        dockerfile.write_text(
            dockerfile.read_text(encoding="utf-8").replace(
                "COPY ai-ready-ingest /workspace/ai-ready-ingest\nCOPY ai-ready-mcp /workspace/ai-ready-mcp\nRUN pip install --no-cache-dir /workspace/ai-ready-ingest /workspace/ai-ready-mcp",
                "COPY . /workspace/osii-mcp\nRUN pip install --no-cache-dir /workspace/osii-mcp",
            ),
            encoding="utf-8",
        )
    if component.startswith("local-") and dockerfile.exists():
        dockerfile.write_text(
            dockerfile.read_text(encoding="utf-8")
            .replace(f"COPY services/{component} /workspace/services/{component}", "COPY . /workspace/service")
            .replace(f"/workspace/services/{component}", "/workspace/service"),
            encoding="utf-8",
        )
        pyproject = component_root / "pyproject.toml"
        pyproject.write_text(
            pyproject.read_text(encoding="utf-8").replace(
                "osii-processor-sdk = { workspace = true }",
                'osii-processor-sdk = { path = "packages/osii-processor-sdk" }',
            ),
            encoding="utf-8",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Export OSII components for separate repositories.")
    parser.add_argument("--output", type=Path, required=True, help="New destination directory for exported components.")
    parser.add_argument("--components", default=",".join(COMPONENTS), help=f"Comma-separated selection: {', '.join(COMPONENTS)}.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned exports without copying.")
    args = parser.parse_args()

    selected = parse_components(args.components)
    output = args.output.expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"Output directory must be new or empty: {output}")
    for component in selected:
        print(f"{component}: {output / component}")
        for entry in COMPONENTS[component]:
            print(f"  {entry.source} -> {entry.destination}")
    if args.dry_run:
        return 0

    output.mkdir(parents=True, exist_ok=True)
    for component in selected:
        component_root = output / component
        component_root.mkdir(parents=True, exist_ok=True)
        for entry in COMPONENTS[component]:
            copy_entry(component_root, entry)
        adapt_container_files(component, component_root)
    write_manifest(output, selected)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
