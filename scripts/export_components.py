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
    "osii-toolbox": (
        ExportEntry("osii-toolbox", "osii-toolbox"),
        ExportEntry("osii-core/processor-sdk", "osii-core/processor-sdk"),
        ExportEntry("docs/reference/processor-api", "docs/reference/processor-api"),
        ExportEntry(".dockerignore", ".dockerignore"),
    ),
    "osii-core": (
        ExportEntry("osii-core", "."),
        ExportEntry("docs/reference/api", "docs/reference/api"),
        ExportEntry("docs/reference/processor-api", "docs/reference/processor-api"),
    ),
    "osii-dashboard": (
        ExportEntry("osii-dashboard/dashboard", "."),
        ExportEntry("docs/reference/api", "docs/reference/api"),
    ),
    "osii-launcher": (
        ExportEntry("osii-launcher", "."),
        ExportEntry("compose.yaml", "compose.yaml"),
    ),
    "osii-mcp": (
        ExportEntry("osii-mcp", "."),
        ExportEntry("docs/reference/api", "docs/reference/api"),
        ExportEntry("docs/reference/processor-api", "docs/reference/processor-api"),
    ),
    "osii-demo-notebooks": (
        ExportEntry("osii-demo-notebooks", "."),
        ExportEntry("docs/tutorials", "docs/tutorials"),
    ),
    "baseline-processors": (
        ExportEntry("osii-core/processor-sdk", "osii-core/processor-sdk"),
        ExportEntry("osii-core/services/local-extractor", "osii-core/services/local-extractor"),
        ExportEntry("osii-core/services/local-tesseract", "osii-core/services/local-tesseract"),
        ExportEntry("osii-core/services/local-synthesizer", "osii-core/services/local-synthesizer"),
        ExportEntry("osii-core/services/local-embedder", "osii-core/services/local-embedder"),
        ExportEntry("osii-core/services/local-enricher", "osii-core/services/local-enricher"),
        ExportEntry("osii-core/services/model-provider-bridge", "osii-core/services/model-provider-bridge"),
        ExportEntry("osii-core/services/baseline-processors", "osii-core/services/baseline-processors"),
        ExportEntry("docs/reference/processor-api", "docs/reference/processor-api"),
        ExportEntry("docs/reference/model-providers.md", "docs/model-providers.md"),
    ),
    "local-extractor": (
        ExportEntry("osii-core/services/local-extractor", "."),
        ExportEntry("osii-core/processor-sdk", "osii-core/processor-sdk"),
        ExportEntry("docs/reference/processor-api", "docs/reference/processor-api"),
    ),
    "local-synthesizer": (
        ExportEntry("osii-core/services/local-synthesizer", "."),
        ExportEntry("osii-core/processor-sdk", "osii-core/processor-sdk"),
        ExportEntry("docs/reference/processor-api", "docs/reference/processor-api"),
    ),
    "local-embedder": (
        ExportEntry("osii-core/services/local-embedder", "."),
        ExportEntry("osii-core/processor-sdk", "osii-core/processor-sdk"),
        ExportEntry("docs/reference/processor-api", "docs/reference/processor-api"),
    ),
    "local-enricher": (
        ExportEntry("osii-core/services/local-enricher", "."),
        ExportEntry("osii-core/processor-sdk", "osii-core/processor-sdk"),
        ExportEntry("docs/reference/processor-api", "docs/reference/processor-api"),
    ),
    "model-provider-bridge": (
        ExportEntry("osii-core/services/model-provider-bridge", "."),
        ExportEntry("osii-core/processor-sdk", "osii-core/processor-sdk"),
        ExportEntry("docs/reference/model-providers.md", "docs/model-providers.md"),
        ExportEntry("docs/reference/processor-api", "docs/reference/processor-api"),
    ),
}

IGNORED_NAMES = {
    ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv",
    "__pycache__", "node_modules", "dist", "build", ".vite",
    "gen", "target", "data_volume", "osii-data", "models", ".cache", "osii-env", ".env",
}


def is_generated(name: str) -> bool:
    return (
        name in IGNORED_NAMES
        or name.startswith((".venv", ".env."))
        or name.endswith((".pyc", ".pyo", ".egg-info"))
    )


def ignore_generated(_: str, names: list[str]) -> set[str]:
    return {name for name in names if is_generated(name)}


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
    if source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return
    if entry.destination == ".":
        destination.mkdir(parents=True, exist_ok=True)
        for child in source.iterdir():
            if is_generated(child.name):
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
            "osii-core": "Publish the osii Python package to the corporate package registry before exporting MCP consumers.",
            "osii-dashboard": "Configure its API endpoint for the deployed OSII backend.",
            "osii-launcher": "Build and sign desktop installers separately from the container images.",
            "osii-toolbox": "Processor services use the shared osii-processor-sdk contract package.",
        },
    }
    (output / "EXPORT_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def adapt_container_files(component: str, component_root: Path) -> None:
    """Adapt repository-relative files to an exported component root."""
    dockerfile = component_root / "Dockerfile"
    if component == "osii-launcher":
        config = component_root / "src-tauri" / "tauri.conf.json"
        content = config.read_text(encoding="utf-8")
        config.write_text(
            content.replace('"../../compose.yaml": "deployment/compose.yaml"', '"../compose.yaml": "deployment/compose.yaml"'),
            encoding="utf-8",
        )
    if component == "osii-core" and dockerfile.exists():
        content = dockerfile.read_text(encoding="utf-8")
        content = content.replace("COPY osii-core/processor-sdk ./processor-sdk", "COPY processor-sdk ./processor-sdk")
        content = content.replace("COPY osii-core/pyproject.toml osii-core/README.md ./", "COPY pyproject.toml README.md ./")
        content = content.replace("COPY osii-core/osii ./osii", "COPY osii ./osii")
        content = content.replace("COPY osii-core/config ./config", "COPY config ./config")
        dockerfile.write_text(content, encoding="utf-8")
    if component == "osii-mcp" and dockerfile.exists():
        dockerfile.write_text(
            dockerfile.read_text(encoding="utf-8").replace(
                "COPY osii-core /workspace/osii-core\n"
                "COPY osii-mcp /workspace/osii-mcp\n"
                "RUN \"${VIRTUAL_ENV}/bin/python\" -m pip install --no-cache-dir \\\n"
                "    /workspace/osii-core/processor-sdk \\\n"
                "    /workspace/osii-core \\\n"
                "    /workspace/osii-mcp && \\\n",
                "COPY . /workspace/osii-mcp\n"
                "RUN \"${VIRTUAL_ENV}/bin/python\" -m pip install --no-cache-dir "
                "/workspace/osii-mcp && \\\n",
            ),
            encoding="utf-8",
        )
    if component.startswith("local-") or component == "model-provider-bridge":
        pyproject = component_root / "pyproject.toml"
        pyproject.write_text(
            pyproject.read_text(encoding="utf-8").replace(
                'osii-processor-sdk = { path = "../../processor-sdk", editable = true }',
                'osii-processor-sdk = { path = "osii-core/processor-sdk", editable = true }',
            ),
            encoding="utf-8",
        )
        port = {
            "local-extractor": 8092,
            "local-synthesizer": 8093,
            "local-embedder": 8085,
            "local-enricher": 8094,
            "model-provider-bridge": 8095,
        }[component]
        dockerfile.write_text(
            "ARG OSII_BASE_IMAGE=registry.access.redhat.com/ubi9/ubi:latest\n"
            "FROM ${OSII_BASE_IMAGE}\n"
            "ARG OSII_PYTHON_VERSION=3.12\n"
            "ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \\\n"
            "    VIRTUAL_ENV=/opt/venv \\\n"
            "    PATH=/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n"
            "RUN dnf install -y \"python${OSII_PYTHON_VERSION}\" \"python${OSII_PYTHON_VERSION}-pip\" shadow-utils ca-certificates && \\\n"
            "    dnf clean all && rm -rf /var/cache/dnf && \\\n"
            "    \"python${OSII_PYTHON_VERSION}\" -m venv \"${VIRTUAL_ENV}\" && \\\n"
            "    \"${VIRTUAL_ENV}/bin/python\" -m pip install --no-cache-dir --upgrade pip\n"
            "WORKDIR /workspace\n"
            "COPY osii-core/processor-sdk /workspace/osii-core/processor-sdk\n"
            "COPY . /workspace/service\n"
            "RUN \"${VIRTUAL_ENV}/bin/python\" -m pip install --no-cache-dir "
            "/workspace/osii-core/processor-sdk /workspace/service && \\\n"
            "    groupadd --system osii && \\\n"
            "    useradd --system --gid osii --home-dir /workspace osii && \\\n"
            "    chown -R osii:osii /workspace\n"
            "USER osii\n"
            f"EXPOSE {port}\n"
            f'CMD ["uvicorn", "app.main:app", "--app-dir", "/workspace/service", "--host", "0.0.0.0", "--port", "{port}"]\n',
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
