"""Selective corporate release decisions, without registry or runner access."""

import hashlib
import importlib
import json
from pathlib import Path

import pytest

from scripts.corporate_config import load_defaults, render_files
from scripts.release_plan import IMAGES, Plan, check_scope


@pytest.mark.parametrize(
    ("scope", "expected", "package"),
    [
        ("full", IMAGES, True),
        ("core", tuple(image for image in IMAGES if image != "dashboard"), True),
        ("ui", ("dashboard",), False),
        ("launcher", (), False),
        ("toolbox-tesseract-opencv", ("tesseract-opencv",), False),
        ("toolbox-tabular", ("tabular",), False),
        ("toolbox-llm-wikis", ("llm-wikis",), False),
    ],
)
def test_release_scopes(scope: str, expected: tuple[str, ...], package: bool) -> None:
    plan = Plan("1.2.3", "v1.2.2", scope, "1.2.3" if package else "1.2.2")
    assert plan.images_to_build == expected
    assert plan.publish_package is package


def test_ui_release_rejects_core_or_shared_build_changes() -> None:
    plan = Plan("1.2.3", "v1.2.2", "ui", "1.2.2")
    check_scope(plan, ["osii-dashboard/dashboard/src/App.tsx", "osii-launcher/package.json"])
    with pytest.raises(ValueError, match="osii-core/osii/main.py"):
        check_scope(plan, ["osii-dashboard/dashboard/src/App.tsx", "osii-core/osii/main.py"])
    with pytest.raises(ValueError, match="compose.yaml"):
        check_scope(plan, ["compose.yaml"])


@pytest.mark.parametrize("scope", [
    "full", "core", "ui", "launcher", "toolbox-tesseract-opencv",
    "toolbox-tabular", "toolbox-llm-wikis",
])
def test_prepare_dry_run_does_not_edit_versions(
    scope: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import release_plan

    files = {
        "osii-launcher/package.json": '{"version": "0.1.0"}\n',
        "osii-launcher/package-lock.json":
            '{"version": "0.1.0", "packages": {"": {"version": "0.1.0"}}}\n',
        "osii-launcher/src-tauri/Cargo.toml": '[package]\nversion = "0.1.0"\n',
        "osii-launcher/src-tauri/Cargo.lock":
            '[[package]]\nname = "osii-launcher"\nversion = "0.1.0"\n',
        "osii-launcher/src-tauri/tauri.conf.json": '{"version": "0.1.0"}\n',
        "osii-core/pyproject.toml": '[project]\nversion = "0.1.0"\n',
        "release.toml": 'version = "0.1.0"\n',
    }
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    monkeypatch.setattr(release_plan, "ROOT", tmp_path)
    monkeypatch.setattr(release_plan, "PLAN_FILE", tmp_path / "release.toml")
    monkeypatch.setattr(release_plan, "load_plan", lambda: Plan("0.1.0", "", "full", "0.1.0"))
    monkeypatch.setattr(release_plan, "_git", lambda *args: "")
    monkeypatch.setattr(release_plan, "_build_defaults_changed", lambda tag: False)
    monkeypatch.setattr(release_plan.subprocess, "run", lambda *args, **kwargs: None)
    plan = release_plan.prepare("0.1.1", scope, "v0.1.0", dry_run=True)
    assert plan.scope == scope
    assert {(name, (tmp_path / name).read_text(encoding="utf-8")) for name in files} == set(files.items())


def test_corporate_defaults_are_non_secret_and_generate_pinned_local_settings(tmp_path: Path) -> None:
    config = tmp_path / "osii.toml"
    config.write_text(
        "[defaults]\n"
        'OSII_QUAY_REGISTRY = "quay.corp.test"\n'
        'OSII_IMAGE_PREFIX = "quay.corp.test/team/osii"\n'
        f'OSII_BASE_IMAGE = "quay.corp.test/ubi@sha256:{"a" * 64}"\n'
        'OSII_TESSERACT_SOURCE_URL = "https://artifacts.corp.test/tess.tar.gz"\n'
        'OSII_LEPTONICA_SOURCE_URL = "https://artifacts.corp.test/lep.tar.gz"\n'
        'OSII_TESSDATA_BASE_URL = "https://artifacts.corp.test/data"\n'
        'OSII_MODEL_BASE_URL = "https://models.corp.test/v1"\n',
        encoding="utf-8",
    )
    defaults = load_defaults(config)
    rendered = render_files(defaults, "1.2.3")
    launcher = next(value for path, value in rendered.items() if path.name == ".env.local")
    assert 'VITE_OSII_IMAGE_TAG="1.2.3"' in launcher
    assert all("API_KEY=" not in value for value in rendered.values())
    with pytest.raises(ValueError, match="immutable"):
        render_files(defaults, "latest")
    config.write_text(config.read_text() + 'OPENAI_API_KEY = "secret"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="unknown"):
        load_defaults(config)


def test_release_plan_file_is_valid() -> None:
    root = Path(__file__).resolve().parents[2]
    from scripts.release_plan import load_plan

    plan = load_plan(root / "release.toml")
    assert json.loads((root / "osii-launcher/package.json").read_text())["version"] == plan.version


def test_latest_promotion_copies_verified_multiarch_release_only(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "scripts"))
    release = importlib.import_module("corporate_release")
    manifest = json.dumps({"manifests": [
        {"platform": {"os": "linux", "architecture": "amd64"}},
        {"platform": {"os": "linux", "architecture": "arm64"}},
    ]}).encode()
    commands: list[tuple[str, ...]] = []
    monkeypatch.setenv("CI_COMMIT_TAG", "v1.2.3")
    monkeypatch.setenv("OSII_IMAGE_PREFIX", "quay.corp.test/team/osii")
    monkeypatch.setattr(release, "preflight", lambda: "1.2.3")
    monkeypatch.setattr(release, "api_request", lambda *args, **kwargs: b"{}")
    monkeypatch.setattr(release, "registry_login", lambda *args: None)
    monkeypatch.setattr(release.subprocess, "check_output", lambda *args, **kwargs: manifest)
    monkeypatch.setattr(release, "run", lambda *command, **kwargs: commands.append(command))
    release.promote_latest()
    digest = hashlib.sha256(manifest).hexdigest()
    assert len(commands) == len(IMAGES)
    assert all(command[:4] == ("skopeo", "copy", "--all", "--preserve-digests")
               for command in commands)
    assert all(command[-1].endswith(":latest") and f"@sha256:{digest}" in command[-2]
               for command in commands)


def test_multiarch_verification_rejects_missing_architecture(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "scripts"))
    release = importlib.import_module("corporate_release")
    only_amd64 = json.dumps({"manifests": [
        {"platform": {"os": "linux", "architecture": "amd64"}},
    ]}).encode()
    with pytest.raises(ValueError, match="Incomplete multi-architecture"):
        release._verified_platforms(only_amd64, "quay.corp.test/team/osii-core:1.2.3")
