"""Selective corporate release decisions, without registry or runner access."""

import hashlib
import importlib
import json
import shutil
import zipfile
from argparse import Namespace
from pathlib import Path

import pytest

from scripts.corporate_config import load_defaults, render_files
from scripts.launcher_catalog import CatalogError, update_catalog, validate_catalog
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
        'OSII_IMAGE_PREFIX = "quay.corp.test/ai-ready-everything/osii"\n'
        f'OSII_BASE_IMAGE = "quay.corp.test/ubi@sha256:{"a" * 64}"\n'
        'OSII_TESSERACT_SOURCE_URL = "https://artifacts.corp.test/tess.tar.gz"\n'
        'OSII_LEPTONICA_SOURCE_URL = "https://artifacts.corp.test/lep.tar.gz"\n'
        'OSII_TESSDATA_BASE_URL = "https://artifacts.corp.test/data"\n'
        'OSII_MODEL_BASE_URL = "https://models.corp.test/v1"\n'
        'OSII_CATALOG_URL = "https://gitlab.corp.test/osii/catalog/-/raw/main/catalog.json"\n',
        encoding="utf-8",
    )
    defaults = load_defaults(config)
    rendered = render_files(defaults, "1.2.3")
    launcher = next(value for path, value in rendered.items() if path.name == ".env.local")
    assert 'VITE_OSII_IMAGE_TAG="1.2.3"' in launcher
    assert 'VITE_OSII_CATALOG_URL="https://gitlab.corp.test/osii/catalog/-/raw/main/catalog.json"' in launcher
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


def test_launcher_catalog_adds_a_complete_stack_and_independent_optional_images() -> None:
    registry = "quay.corp.test"
    digest = lambda character: f"sha256:{character * 64}"
    old = {
        "version": 1,
        "registry": registry,
        "namespace": "ai-ready-everything",
        "stacks": [{
            "id": "1.2.2", "displayName": "OSII 1.2.2",
            "images": {
                "release": "1.2.2",
                "core": f"{registry}/ai-ready-everything/osii-core@{digest('a')}",
                "dashboard": f"{registry}/ai-ready-everything/osii-dashboard@{digest('a')}",
                "baselineProcessors": f"{registry}/ai-ready-everything/osii-baseline-processors@{digest('a')}",
            },
        }],
        "tools": [],
        "images": [],
    }
    updated = update_catalog(
        old,
        release="1.2.3",
        image_digests={
            "core": digest("b"), "dashboard": digest("c"), "baseline-processors": digest("d"),
            "tesseract-opencv": digest("e"), "tabular": digest("f"), "llm-wikis": digest("0"),
        },
        published_images=("core", "dashboard", "baseline-processors", "tesseract-opencv", "tabular"),
    )
    assert [stack["id"] for stack in updated["stacks"]] == ["1.2.2", "1.2.3"]
    assert updated["stacks"][-1]["images"]["baselineProcessors"].endswith("@" + digest("d"))
    assert updated["tools"][0]["versions"] == [{
        "label": "1.2.3",
        "reference": f"{registry}/ai-ready-everything/osii-tesseract-opencv@{digest('e')}",
    }]
    assert updated["images"][0]["versions"] == [{
        "label": "1.2.3",
        "reference": f"{registry}/ai-ready-everything/osii-tabular@{digest('f')}",
    }]
    assert validate_catalog(updated, registry=registry) == updated
    initial = {**old, "stacks": []}
    stack_digests = {
        "core": digest("b"), "dashboard": digest("c"), "baseline-processors": digest("d"),
    }
    bootstrapped = update_catalog(
        initial, release="1.2.3", image_digests=stack_digests, published_images=(),
    )
    assert bootstrapped["stacks"][0]["images"]["core"].endswith("@" + stack_digests["core"])


def test_launcher_catalog_rejects_tags_and_uppercase_digests() -> None:
    catalog = {
        "version": 1, "registry": "quay.corp.test", "namespace": "ai-ready-everything",
        "stacks": [{
            "id": "1.2.3", "displayName": "OSII 1.2.3",
            "images": {
                "release": "1.2.3",
                "core": "quay.corp.test/ai-ready-everything/osii-core:1.2.3",
                "dashboard": f"quay.corp.test/ai-ready-everything/osii-dashboard@sha256:{'A' * 64}",
                "baselineProcessors": f"quay.corp.test/ai-ready-everything/osii-baseline-processors@sha256:{'a' * 64}",
            },
        }],
        "tools": [], "images": [],
    }
    with pytest.raises(CatalogError, match="lowercase @sha256"):
        validate_catalog(catalog, registry="quay.corp.test")


@pytest.fixture
def manual_release(monkeypatch: pytest.MonkeyPatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "scripts"))
    module = importlib.import_module("corporate_release")
    monkeypatch.setenv("OSII_IMAGE_PREFIX", "quay.corp.test/ai-ready-everything/osii")
    monkeypatch.setenv("OSII_QUAY_REGISTRY", "quay.corp.test")
    monkeypatch.setenv("OSII_BASE_IMAGE", "quay.corp.test/ubi@sha256:" + "a" * 64)
    monkeypatch.setenv("OSII_CATALOG_URL", "https://catalog.corp.test/catalog.json")
    for name in ("OSII_TESSERACT_SOURCE_URL", "OSII_LEPTONICA_SOURCE_URL", "OSII_TESSDATA_BASE_URL"):
        monkeypatch.setenv(name, "https://artifacts.corp.test/source")
    return module


@pytest.mark.parametrize("scope", ["full", "core", "ui", "launcher", "toolbox-tesseract-opencv",
                                   "toolbox-tabular", "toolbox-llm-wikis"])
def test_manual_assembly_only_assembles_selected_and_copies_the_rest(
    scope, manual_release, monkeypatch, tmp_path,
) -> None:
    release = manual_release
    plan = Plan("1.2.3", "v1.2.2", scope, "1.2.3" if scope in {"full", "core"} else "1.2.2")
    raw = json.dumps({"manifests": [
        {"platform": {"os": "linux", "architecture": arch}} for arch in ("amd64", "arm64")
    ]}).encode()
    commands = []
    checked = []
    monkeypatch.setattr(release, "ROOT", tmp_path)
    monkeypatch.setattr(release, "require_new_tag", checked.append)
    monkeypatch.setattr(release, "run", lambda *command, **kwargs: commands.append(command))

    def inspect(command, **kwargs):
        if "--raw" in command:
            return raw
        return json.dumps({"Os": "linux", "Architecture": command[-1].rsplit("-", 1)[1]}).encode()

    monkeypatch.setattr(release.subprocess, "check_output", inspect)
    release.assemble_images(plan.version, plan)
    copies = [command for command in commands if command[0] == "skopeo"]
    assert len(copies) == len(IMAGES) - len(plan.images_to_build)
    assert all(command[1:4] == ("copy", "--all", "--preserve-digests") for command in copies)
    manifests = [command for command in commands if "scripts/publish_multiarch.py" in command]
    assert len(manifests) == bool(plan.images_to_build)
    if manifests:
        command = manifests[0]
        assert command[command.index("--phase") + 1] == "manifest"
        assert command[command.index("--include") + 1:] == plan.images_to_build
    assert len(checked) == 6
    records = json.loads((tmp_path / "release/images.json").read_text())
    assert len(records) == 6
    assert set(records.values()) == {"sha256:" + hashlib.sha256(raw).hexdigest()}


def test_manual_assembly_fails_before_writes_when_previous_arch_is_missing(
    manual_release, monkeypatch,
) -> None:
    release = manual_release
    monkeypatch.setattr(release, "require_new_tag", lambda reference: None)
    monkeypatch.setattr(release.subprocess, "check_output", lambda *args, **kwargs: b'{"manifests": []}')
    monkeypatch.setattr(release, "run", lambda *args, **kwargs: pytest.fail("must not write tags"))
    with pytest.raises(ValueError, match="Incomplete"):
        release.assemble_images("1.2.3", Plan("1.2.3", "v1.2.2", "launcher", "1.2.2"))


@pytest.mark.parametrize("scope", ["full", "core", "ui", "launcher", "toolbox-tesseract-opencv",
                                   "toolbox-tabular", "toolbox-llm-wikis"])
def test_manual_dry_run_does_not_build_or_publish(scope, manual_release, monkeypatch, capsys) -> None:
    release = manual_release
    plan = Plan("1.2.3", "v1.2.2", scope, "1.2.3" if scope in {"full", "core"} else "1.2.2")
    monkeypatch.setattr(release, "load_defaults", lambda path: dict(release.os.environ))
    monkeypatch.setattr(release, "manual_preflight", lambda **kwargs: plan)
    monkeypatch.setattr(release, "run", lambda *args, **kwargs: pytest.fail("must not execute commands"))
    for action in ("images", "assemble", "installer", "bundle", "catalog", "promote-latest"):
        release.manual_action(Namespace(config=Path("unused"), dry_run=True, action=action))
    output = capsys.readouterr().out
    assert "no builds" in output
    if scope == "launcher":
        assert "Build: no images" in output


def test_manual_image_build_rejects_wrong_engine(manual_release, monkeypatch) -> None:
    release = manual_release
    monkeypatch.setattr(release, "load_plan", lambda: Plan("1.2.3", "v1.2.2", "ui", "1.2.2"))
    monkeypatch.setattr(release.subprocess, "check_output", lambda *args, **kwargs: "linux/arm64\n")
    monkeypatch.setattr(release, "run", lambda *args, **kwargs: pytest.fail("must not build"))
    with pytest.raises(ValueError, match="native linux/amd64"):
        release.build_images("1.2.3", arch="amd64")


def test_manual_preflight_rejects_dirty_or_wrong_tag(manual_release, monkeypatch) -> None:
    release = manual_release
    monkeypatch.setattr(release, "check_release_plan", lambda: Plan("1.2.3", "v1.2.2", "ui", "1.2.2"))
    monkeypatch.setattr(release.subprocess, "check_output", lambda *args, **kwargs: " M changed.py\n")
    with pytest.raises(ValueError, match="clean, committed"):
        release.manual_preflight()
    results = iter(["", "tagcommit", "othercommit"])
    monkeypatch.setattr(release.subprocess, "check_output", lambda *args, **kwargs: next(results))
    with pytest.raises(ValueError, match="Check out v1.2.3 exactly"):
        release.manual_preflight()


def test_manual_bundle_filters_stale_files_and_marks_missing_targets(
    manual_release, monkeypatch, tmp_path,
) -> None:
    release = manual_release
    shutil.copy2(release.ROOT / "compose.yaml", tmp_path / "compose.yaml")
    monkeypatch.setattr(release, "ROOT", tmp_path)
    monkeypatch.setattr(release, "_release_image_digests", lambda version: {name: "sha256:" + "a" * 64 for name in IMAGES})
    monkeypatch.setattr(release.subprocess, "check_output", lambda *args, **kwargs: "abc123")
    installers = tmp_path / "release/installers"
    installers.mkdir(parents=True)
    (installers / "OSII-1.2.3-windows-x64.exe").write_bytes(b"test placeholder, not a signed executable")
    (installers / "OSII-0.0.1-windows-x64.exe").write_bytes(b"stale")
    packages = tmp_path / "release/python"
    packages.mkdir()
    (packages / "osii-0.0.1-py3-none-any.whl").write_bytes(b"stale")
    plan = Plan("1.2.3", "v1.2.2", "ui", "1.2.2")
    release.manual_bundle(plan, ["windows-x64"])
    staged = tmp_path / "release/1.2.3"
    assert not list(staged.glob("*.whl"))
    assert not list(staged.glob("*0.0.1*"))
    notes = (staged / "RELEASE-NOTES.md").read_text()
    assert "macos-arm64" in notes and "reused from the prior release" in notes
    for record in (staged / "SHA256SUMS").read_text().splitlines():
        digest, name = record.split("  ", 1)
        assert hashlib.sha256((staged / name).read_bytes()).hexdigest() == digest
    with zipfile.ZipFile(staged / "deployment.zip") as archive:
        import yaml
        compose = yaml.safe_load(archive.read("compose.yaml"))
        assert all("build" not in service for service in compose["services"].values())
        assert compose["services"]["api"]["environment"]["OSII_OLLAMA_ALLOWED_MODELS"] == (
            "${OSII_OLLAMA_ALLOWED_MODELS-all-minilm,llama3.2:1b}"
        )
        assert "mcp" not in compose["services"] and "tika" not in compose["services"]
        defaults = archive.read(".env.example").decode()
        assert 'OSII_CONFIG_DIR_HOST="./osii-data/config"' in defaults
        assert 'OSII_ALLOW_LOCAL_CONFIG_WRITES="true"' in defaults
        assert 'OSII_DEFAULT_SYNTHESIZER="local.extractive-preview"' in defaults
        assert 'OSII_DEFAULT_EMBEDDER="local.hashing"' in defaults
        assert "API_KEY=" not in defaults and "CA_BUNDLE=" not in defaults
    with pytest.raises(ValueError, match="already exists"):
        release.manual_bundle(plan, ["windows-x64"])


def test_manual_bundle_needs_matching_core_artifacts(manual_release, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(manual_release, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="matching osii wheel"):
        manual_release.manual_bundle(Plan("1.2.3", "v1.2.2", "core", "1.2.3"), ["none"])


def test_manual_catalog_bootstrap_and_preservation(manual_release, monkeypatch, tmp_path) -> None:
    release = manual_release
    monkeypatch.setattr(release, "ROOT", tmp_path)
    monkeypatch.setattr(release, "_verify_catalog_digest", lambda reference: None)
    digests = {name: "sha256:" + "a" * 64 for name in IMAGES}
    monkeypatch.setattr(release, "_release_image_digests", lambda version: digests)
    release.manual_catalog(Plan("1.2.2", "", "full", "1.2.2"), None, first=True)
    source = tmp_path / "prior.json"
    shutil.copy2(tmp_path / "release/catalog.json", source)
    release.manual_catalog(Plan("1.2.3", "v1.2.2", "ui", "1.2.2"), source, first=False)
    catalog = json.loads((tmp_path / "release/catalog.json").read_text())
    assert [stack["id"] for stack in catalog["stacks"]] == ["1.2.2", "1.2.3"]
    assert catalog["tools"][0]["versions"][0]["label"] == "1.2.2"
    with pytest.raises(ValueError, match="not both"):
        release.manual_catalog(Plan("1.2.3", "v1.2.2", "ui", "1.2.2"), source, first=True)


def test_prepare_keeps_local_python_lock_version_in_sync(tmp_path, monkeypatch) -> None:
    from scripts import release_plan
    root = release_plan.ROOT
    for name in ("release.toml", "uv.lock", "osii-core/pyproject.toml", "osii-launcher/package.json",
                 "osii-launcher/package-lock.json", "osii-launcher/src-tauri/Cargo.toml",
                 "osii-launcher/src-tauri/Cargo.lock", "osii-launcher/src-tauri/tauri.conf.json"):
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / name, destination)
    monkeypatch.setattr(release_plan, "ROOT", tmp_path)
    monkeypatch.setattr(release_plan, "PLAN_FILE", tmp_path / "release.toml")
    plan = release_plan.prepare("99.0.0", "full", "")
    release_plan.check(plan, compare=False)
    assert 'name = "osii"\nversion = "99.0.0"' in (tmp_path / "uv.lock").read_text()
