"""Check Toolbox packaging without a container runtime or model downloads."""

from __future__ import annotations

import importlib.util
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
TOOLS = (
    "osii-tesseract",
    "tabular-dataset-processors",
    "minilm-embedding-service",
    "model2vec-embedder",
)


@pytest.mark.parametrize("tool", TOOLS)
def test_container_copy_sources_exist(tool):
    directory = ROOT / "osii-toolbox" / tool
    context = directory if tool == "minilm-embedding-service" else ROOT
    for line in (directory / "Dockerfile").read_text().splitlines():
        if line.startswith("COPY "):
            for source in shlex.split(line)[1:-1]:
                assert (context / source).exists(), (tool, source)


def test_tools_do_not_join_core_workspace_or_duplicate_sdk():
    workspace = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["uv"]["workspace"]
    assert "osii-toolbox/*" in workspace["exclude"]
    assert all(not member.startswith("osii-toolbox/") for member in workspace["members"])
    assert not (ROOT / "osii-toolbox" / "packages").exists()
    for tool in TOOLS:
        manifest = ROOT / "osii-toolbox" / tool / "pyproject.toml"
        if manifest.exists():
            source = tomllib.loads(manifest.read_text())["tool"]["uv"]["sources"]["osii-processor-sdk"]
            assert (manifest.parent / source["path"]).resolve() == ROOT / "osii-core" / "processor-sdk"


def test_repository_uses_named_component_roots():
    for legacy_root in ("ai-ready-ingest", "ai-ready-mcp", "packages", "services", "toolbox"):
        assert not (ROOT / legacy_root).exists()
    for component_root in ("osii-core", "osii-dashboard", "osii-mcp", "osii-toolbox"):
        assert (ROOT / component_root).is_dir()


def test_model2vec_image_uses_model2vec_not_baseline_hashing():
    recipe = (ROOT / "osii-toolbox/model2vec-embedder/Dockerfile").read_text()
    assert "osii-core/services/local-embedder" not in recipe
    assert "model2vec-embedder[model2vec]" in recipe
    assert "OSII_LOCAL_EMBEDDING_PROVIDER=model2vec" in recipe
    assert "OSII_OFFLINE=1" in recipe
    assert "OSII_MODEL2VEC_MODEL=/models/model2vec" in recipe


def test_toolbox_export_preserves_build_layout(tmp_path):
    output = tmp_path / "export"
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/export_components.py"),
         "--components", "osii-toolbox", "--output", str(output)],
        check=True, capture_output=True, text=True,
    )
    exported = output / "osii-toolbox"
    assert (exported / "osii-core/processor-sdk/pyproject.toml").is_file()
    assert (exported / ".dockerignore").is_file()
    assert (exported / "osii-toolbox/README.md").is_file()
    for tool in TOOLS:
        assert (exported / "osii-toolbox" / tool / "Dockerfile").is_file()
    assert not list(exported.rglob("*.egg-info"))
    assert not list(exported.rglob("__pycache__"))


def test_core_mcp_and_service_exports_have_standalone_build_paths(tmp_path):
    output = tmp_path / "export"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/export_components.py"),
            "--components",
            "osii-core,osii-mcp,local-extractor",
            "--output",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    core_recipe = (output / "osii-core" / "Dockerfile").read_text()
    assert "COPY processor-sdk /workspace/processor-sdk" in core_recipe
    assert "COPY osii-core/" not in core_recipe

    mcp_recipe = (output / "osii-mcp" / "Dockerfile").read_text()
    assert "COPY . /workspace/osii-mcp" in mcp_recipe
    assert "COPY osii-core" not in mcp_recipe

    service_manifest = tomllib.loads(
        (output / "local-extractor" / "pyproject.toml").read_text()
    )
    source = service_manifest["tool"]["uv"]["sources"]["osii-processor-sdk"]
    assert source["path"] == "osii-core/processor-sdk"


def test_export_omits_runtime_data_and_credentials(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("toolbox_export_test", ROOT / "scripts/export_components.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    source = tmp_path / "source"
    source.mkdir()
    (source / "processor.py").write_text("# source\n")
    for name in ("models", ".cache", ".venv312", "package.egg-info", ".git"):
        (source / name).mkdir()
        (source / name / "ignored").write_text("runtime data")
    for name in (".env", ".env.production", "cached.pyc"):
        (source / name).write_text("not for export")
    monkeypatch.setattr(module, "REPOSITORY_ROOT", tmp_path)
    for destination in (".", "nested"):
        target = tmp_path / ("flat" if destination == "." else "tree")
        module.copy_entry(target, module.ExportEntry("source", destination))
        assert [path.name for path in (target / destination).iterdir()] == ["processor.py"]
