from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("osii_dev_stack", ROOT / "scripts" / "dev_stack.py")
assert SPEC and SPEC.loader
DEV_STACK = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = DEV_STACK
SPEC.loader.exec_module(DEV_STACK)


def test_supervisor_http_requires_private_token(tmp_path):
    supervisor = DEV_STACK.CapabilitySupervisor(
        services=[],
        env={
            "OSII_TIKA_PORT": "19998",
        },
        uv="uv",
        token="private-token",
    )
    supervisor.start_http(0)
    assert supervisor.server is not None
    port = supervisor.server.server_address[1]
    try:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/services"):
                raise AssertionError("unauthenticated request unexpectedly succeeded")
        except urllib.error.HTTPError as exc:
            assert exc.code == 403

        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/services",
            headers={"Authorization": "Bearer private-token"},
        )
        with urllib.request.urlopen(request) as response:
            payload = json.load(response)
        assert payload["services"] == []  # No implicit Apache Tika service.
    finally:
        supervisor.close()


def test_supervisor_rejects_unknown_services_and_actions():
    supervisor = DEV_STACK.CapabilitySupervisor(
        services=DEV_STACK.toolbox_services("uv", {"OSII_START_TOOLBOX": "false"}),
        env={},
        uv="uv",
        token="private-token",
    )
    try:
        supervisor.action("arbitrary-command", "start")
        raise AssertionError("unknown service unexpectedly accepted")
    except KeyError:
        pass
    try:
        supervisor.action("tika", "run-shell")
        raise AssertionError("unknown action unexpectedly accepted")
    except ValueError:
        pass


def test_service_plan_uses_nested_components_without_concurrent_uv_sync():
    services = DEV_STACK.service_commands(
        "uv",
        "npm",
        {
            "OSII_API_PORT": "8511",
            "OSII_DASHBOARD_PORT": "5173",
            "OSII_MCP_PORT": "8022",
            "OSII_EMBEDDINGS_PORT": "8085",
        },
        core_only=False,
    )

    by_name = {service.name: service for service in services}
    assert by_name["api"].working_directory == ROOT / "osii-core"
    assert by_name["mcp"].working_directory == ROOT / "osii-mcp"
    assert by_name["extractor"].working_directory == (
        ROOT / "osii-core" / "services" / "local-extractor"
    )
    assert by_name["ocr"].working_directory == (
        ROOT / "osii-core" / "services" / "local-tesseract"
    )
    assert by_name["ocr"].port == 8080
    for service in services:
        if service.command[0] == "uv" and service.start_automatically:
            assert "--no-sync" in service.command
    assert by_name["readable-wiki"].start_automatically is True
    assert by_name["readable-wiki"].working_directory == (
        ROOT / "osii-toolbox" / "llm-wiki-enrichers"
    )
    assert by_name["concept-entity-wiki"].port == 8100
    assert by_name["tesseract-opencv"].port == 8081
    assert by_name["tesseract-opencv"].working_directory == (
        ROOT / "osii-toolbox" / "osii-tesseract"
    )
    assert by_name["csv-extractor"].port == 8097
    assert by_name["collection-table"].port == 8098
    assert by_name["banyan"].port == 8101
    assert by_name["banyan"].working_directory == ROOT / "osii-toolbox" / "banyan-nemotron-parse"
    assert "banyan_extract.integrations.osii_extractor:app" in by_name["banyan"].command
    environments = {dict(service.environment)["UV_PROJECT_ENVIRONMENT"]
                    for service in services if service.working_directory.is_relative_to(ROOT / "osii-toolbox")}
    assert len(environments) == 5
    assert by_name["tika"].working_directory == ROOT / "osii-toolbox" / "tika-adapter"
    assert "tika_adapter.main:app" in by_name["tika"].command
    assert by_name["tika"].port == 8102
    assert str(ROOT / "osii-env") not in environments


def test_toolbox_opt_out_retains_manual_controls_and_core_only_omits_services():
    env = {"OSII_START_TOOLBOX": "false"}
    services = DEV_STACK.service_commands("uv", "npm", env, core_only=False)
    tools = [s for s in services if s.working_directory.is_relative_to(ROOT / "osii-toolbox")]
    assert len(tools) == 7 and all(not s.start_automatically for s in tools)
    assert all("--no-sync" not in s.command for s in tools)
    core = DEV_STACK.service_commands("uv", "npm", {}, core_only=True)
    assert {s.name for s in core} == {"api", "worker", "inventory-worker", "mcp", "dashboard"}
    by_name = {s.name: s for s in core}
    assert "osii.main:app" in by_name["api"].command
    assert "python -m osii.worker" in by_name["worker"].command
    assert "python -m osii.volume.worker" in by_name["inventory-worker"].command


def test_toolbox_environment_registers_custom_ports_without_changing_routes(monkeypatch, tmp_path):
    (tmp_path / "source").mkdir()
    monkeypatch.setattr(DEV_STACK, "load_dotenv", lambda _path: {})
    monkeypatch.setenv("OSII_SOURCE_DIR", str(tmp_path / "source"))
    monkeypatch.setenv("OSII_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("OSII_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OSII_START_TOOLBOX", "true")
    monkeypatch.setenv("OSII_TESSERACT_OPENCV_PORT", "18081")
    monkeypatch.setenv("OSII_BANYAN_PORT", "18101")
    monkeypatch.setenv("OSII_PROCESSORS", "http://processor.test:9999")
    env = DEV_STACK.build_environment(core_only=False)
    urls = env["OSII_PROCESSORS"].split(",")
    assert "http://127.0.0.1:18081" in urls
    assert "http://127.0.0.1:8097" in urls
    assert "http://127.0.0.1:8098" in urls
    assert "http://127.0.0.1:18101" in urls
    assert "http://processor.test:9999" in urls
    assert env["OSII_DEFAULT_EXTRACTOR"] == "local.native-text"
    monkeypatch.setenv("OSII_START_TOOLBOX", "false")
    assert "http://127.0.0.1:18081" in DEV_STACK.build_environment(False)["OSII_PROCESSORS"].split(",")


@pytest.mark.parametrize("enabled, core_only, expected", [(True, False, 5), (False, False, 0), (True, True, 0)])
def test_toolbox_dependencies_prepare_once_per_isolated_environment(monkeypatch, tmp_path, enabled, core_only, expected):
    dashboard = tmp_path / "osii-dashboard" / "dashboard"
    dashboard.mkdir(parents=True)
    (dashboard / "package-lock.json").write_text("{}")
    (dashboard / "node_modules").mkdir()
    monkeypatch.setattr(DEV_STACK, "REPOSITORY_ROOT", tmp_path)
    calls = []
    monkeypatch.setattr(DEV_STACK.subprocess, "run", lambda command, **kwargs: calls.append((command, kwargs)))
    env = {"UV_PROJECT_ENVIRONMENT": str(tmp_path / "osii-env"), "OSII_START_TOOLBOX": str(enabled)}
    DEV_STACK.prepare_dependencies("uv", "npm", env, core_only=core_only)
    tool_calls = [(cmd, kw) for cmd, kw in calls if kw["cwd"].is_relative_to(tmp_path / "osii-toolbox")]
    assert len(tool_calls) == expected
    assert len({kw["env"]["UV_PROJECT_ENVIRONMENT"] for _, kw in tool_calls}) == expected
    assert all(kw["env"]["UV_PROJECT_ENVIRONMENT"] != env["UV_PROJECT_ENVIRONMENT"] for _, kw in tool_calls)


def test_host_environment_uses_shared_python_default(monkeypatch):
    monkeypatch.setattr(DEV_STACK, "load_dotenv", lambda _path: {})
    monkeypatch.delenv("OSII_PYTHON_VERSION", raising=False)
    env = DEV_STACK.build_environment(core_only=True)
    assert env["UV_PYTHON"] == "3.12"

    monkeypatch.setenv("OSII_PYTHON_VERSION", "3.13")
    env = DEV_STACK.build_environment(core_only=True)
    assert env["UV_PYTHON"] == "3.13"


def test_shared_drive_environment_keeps_artifacts_in_separate_local_root(monkeypatch, tmp_path):
    source = tmp_path / "mounted-share"
    source.mkdir()
    runtime = tmp_path / "local-runtime"
    monkeypatch.setattr(DEV_STACK, "load_dotenv", lambda _path: {})
    monkeypatch.setenv("OSII_SOURCE_DIR", str(source))
    monkeypatch.setenv("OSII_RUNTIME_DIR", str(runtime))
    profile_config = tmp_path / "profiles" / "development" / "deployment"
    monkeypatch.setenv("OSII_CONFIG_DIR_HOST", str(profile_config))
    monkeypatch.delenv("OSII_CONFIG_DIR", raising=False)
    monkeypatch.setenv("OSII_SOURCE_KIND", "shared")
    monkeypatch.delenv("OSII_ROOT", raising=False)
    monkeypatch.delenv("UPLOAD_ORIGINALS_ROOT", raising=False)

    env = DEV_STACK.build_environment(core_only=True)

    assert env["SHARED_VOLUME_ROOT"] == str(source.resolve())
    assert env["OSII_ROOT"] == str((runtime / ".osii").resolve())
    assert env["OSII_INVENTORY_DB"] == str((runtime / ".osii" / "state" / "inventory.sqlite3").resolve())
    assert env["UPLOAD_ORIGINALS_ROOT"] == str((runtime / "uploads").resolve())
    assert env["OSII_SOURCE_KIND"] == "shared"
    assert env["OSII_CONFIG_DIR"] == str(profile_config.resolve())
    assert env["OSII_ENV_FILE"] == str(profile_config.resolve() / "secrets.env")
    assert not (source / ".osii").exists()


def test_shared_drive_environment_does_not_create_missing_source(monkeypatch, tmp_path):
    source = tmp_path / "offline-share"
    monkeypatch.setattr(DEV_STACK, "load_dotenv", lambda _path: {})
    monkeypatch.setenv("OSII_SOURCE_DIR", str(source))

    with pytest.raises(RuntimeError, match="Connect or mount the shared drive"):
        DEV_STACK.build_environment(core_only=True)

    assert not source.exists()


def test_inventory_database_is_checkout_relative_and_outside_source(monkeypatch, tmp_path):
    checkout = tmp_path / "checkout"
    source = checkout / "documents"
    source.mkdir(parents=True)
    monkeypatch.setattr(DEV_STACK, "REPOSITORY_ROOT", checkout)
    monkeypatch.setattr(DEV_STACK, "load_dotenv", lambda _path: {})
    monkeypatch.setenv("OSII_SOURCE_DIR", str(source))
    monkeypatch.setenv("OSII_RUNTIME_DIR", str(checkout / "runtime"))
    monkeypatch.setenv("OSII_VOLUME_DB", "./previous-inventory.sqlite3")
    monkeypatch.delenv("OSII_INVENTORY_DB", raising=False)
    assert DEV_STACK.build_environment(True)["OSII_INVENTORY_DB"] == str(checkout / "previous-inventory.sqlite3")
    monkeypatch.setenv("OSII_INVENTORY_DB", str(source / "unsafe.sqlite3"))
    with pytest.raises(RuntimeError, match="outside the read-only source"):
        DEV_STACK.build_environment(True)
    assert not (source / "unsafe.sqlite3").exists()


@pytest.mark.parametrize("wrapper_default", [False, True])
def test_development_configuration_stays_in_checkout_and_imports_once(monkeypatch, tmp_path, wrapper_default):
    checkout = tmp_path / "checkout"
    source = checkout / "osii-data" / "source"
    source.mkdir(parents=True)
    monkeypatch.setattr(DEV_STACK, "REPOSITORY_ROOT", checkout)
    monkeypatch.setattr(DEV_STACK, "load_dotenv", lambda _path: {})
    monkeypatch.setattr(DEV_STACK.Path, "home", lambda: tmp_path / "home")
    monkeypatch.setattr(DEV_STACK.sys, "platform", "darwin")
    for name in ("OSII_CONFIG_DIR", "OSII_CONFIG_DIR_HOST", "OSII_RUNTIME_DIR", "OSII_SOURCE_DIR", "OSII_ROOT", "UPLOAD_ORIGINALS_ROOT"):
        monkeypatch.delenv(name, raising=False)
    if wrapper_default:
        monkeypatch.setenv("OSII_CONFIG_DIR_HOST", "./osii-data/config")
    previous = tmp_path / "home" / "Library" / "Application Support" / "org.osii.launcher" / "profiles" / "development" / "deployment"
    previous.mkdir(parents=True)
    (previous / "models.toml").write_text('version = 1\n', encoding="utf-8")
    (previous / "secrets.env").write_text('TEST_KEY="test-value"\n', encoding="utf-8")

    env = DEV_STACK.build_environment(core_only=True)

    destination = checkout / "osii-data" / "config"
    assert env["OSII_CONFIG_DIR"] == str(destination)
    assert env["OSII_ENV_FILE"] == str(destination / "secrets.env")
    assert (destination / "secrets.env").read_text() == (previous / "secrets.env").read_text()
    if DEV_STACK.os.name != "nt":
        assert (destination / "secrets.env").stat().st_mode & 0o777 == 0o600
    (destination / "models.toml").write_text('version = 2\n', encoding="utf-8")
    DEV_STACK.build_environment(core_only=True)
    assert (destination / "models.toml").read_text() == 'version = 2\n'
    assert (previous / "models.toml").read_text() == 'version = 1\n'


def test_relative_configuration_override_is_checkout_relative(monkeypatch, tmp_path):
    checkout = tmp_path / "checkout"
    (checkout / "osii-data" / "source").mkdir(parents=True)
    monkeypatch.setattr(DEV_STACK, "REPOSITORY_ROOT", checkout)
    monkeypatch.setattr(DEV_STACK, "load_dotenv", lambda _path: {})
    monkeypatch.setenv("OSII_CONFIG_DIR", "custom-config")
    for name in ("OSII_RUNTIME_DIR", "OSII_SOURCE_DIR", "OSII_ROOT", "UPLOAD_ORIGINALS_ROOT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)

    env = DEV_STACK.build_environment(core_only=True)

    assert env["OSII_CONFIG_DIR"] == str(checkout / "custom-config")


def test_startup_profile_file_and_explicit_routing_survive_launcher(monkeypatch, tmp_path):
    checkout = tmp_path / "checkout"
    source = checkout / "source"
    source.mkdir(parents=True)
    profile = checkout / ".env.corporate"
    profile.write_text(f'OSII_SOURCE_DIR={source}\nOSII_CHAT_BASE_URL=https://models.test/v1\nOSII_DEFAULT_EXTRACTOR=toolbox.tesseract-opencv\nCHAT_PROVIDER=openai\nCHAT_PROVIDER_CHAIN=openai,extractive\n')
    monkeypatch.setattr(DEV_STACK, "REPOSITORY_ROOT", checkout)
    monkeypatch.setenv("OSII_STARTUP_ENV", ".env.corporate")
    monkeypatch.setenv("OSII_MODEL_BRIDGE_PORT", "18095")
    monkeypatch.setenv("OSII_CONFIG_DIR", str(tmp_path / "config"))
    for key in ("OSII_SOURCE_DIR", "OSII_DEFAULT_EXTRACTOR", "CHAT_PROVIDER", "CHAT_PROVIDER_CHAIN", "OSII_INVENTORY_DB", "OSII_VOLUME_DB", "OSII_ROOT", "OSII_RUNTIME_DIR"):
        monkeypatch.delenv(key, raising=False)
    env = DEV_STACK.build_environment(False)
    assert env["SHARED_VOLUME_ROOT"] == str(source)
    assert env["OSII_DEFAULT_EXTRACTOR"] == "toolbox.tesseract-opencv"
    assert env["CHAT_PROVIDER_CHAIN"] == "openai,extractive"
    assert env["OSII_DEFAULT_SYNTHESIZER"] == "openai.synthesizer"
    assert "http://127.0.0.1:18095/openai/synthesizer" in env["OSII_PROCESSORS"]
    assert "http://127.0.0.1:8095/openai/synthesizer" not in env["OSII_PROCESSORS"]
    monkeypatch.setenv("OSII_DEFAULT_EXTRACTOR", "local.native-text")
    assert DEV_STACK.build_environment(False)["OSII_DEFAULT_EXTRACTOR"] == "local.native-text"


def test_default_startup_leaves_chat_selection_to_saved_models(monkeypatch, tmp_path):
    checkout = tmp_path / "checkout"
    source = checkout / "source"
    source.mkdir(parents=True)
    monkeypatch.setattr(DEV_STACK, "REPOSITORY_ROOT", checkout)
    monkeypatch.setattr(DEV_STACK, "load_dotenv", lambda _: {"OSII_SOURCE_DIR": str(source)})
    monkeypatch.setenv("OSII_CONFIG_DIR", str(tmp_path / "config"))
    for name in ("CHAT_PROVIDER", "CHAT_PROVIDER_CHAIN", "CHAT_MODEL", "OSII_SOURCE_DIR", "OSII_ROOT", "OSII_RUNTIME_DIR", "OSII_INVENTORY_DB", "OSII_VOLUME_DB"):
        monkeypatch.delenv(name, raising=False)
    env = DEV_STACK.build_environment(False)
    assert "CHAT_PROVIDER" not in env
    assert "CHAT_PROVIDER_CHAIN" not in env


def test_public_env_template_uses_current_model_and_endpoint_keys():
    settings = DEV_STACK.load_dotenv(ROOT / ".env.example")
    assert {"OSII_CHAT_MODEL", "OSII_EMBEDDING_MODEL", "OPENAI_BASE_URL"} <= settings.keys()
    assert not ({"CHAT_PROVIDER", "CHAT_PROVIDER_CHAIN", "CHAT_MODEL", "OSII_MODEL_BASE_URL", "OSII_MODEL_API_KEY", "OPENAI_CHAT_MODEL", "OPENAI_SYNTHESIS_MODEL"} & settings.keys())
