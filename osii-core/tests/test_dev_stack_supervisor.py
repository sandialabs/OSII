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
        assert {item["id"] for item in payload["services"]} == {"tika"}
    finally:
        supervisor.close()


def test_supervisor_rejects_unknown_services_and_actions():
    supervisor = DEV_STACK.CapabilitySupervisor(
        services=[],
        env={"OSII_TIKA_PORT": "19998"},
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
        if service.command[0] == "uv":
            assert "--no-sync" in service.command


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
    monkeypatch.setenv("OSII_SOURCE_KIND", "shared")
    monkeypatch.delenv("OSII_ROOT", raising=False)
    monkeypatch.delenv("UPLOAD_ORIGINALS_ROOT", raising=False)

    env = DEV_STACK.build_environment(core_only=True)

    assert env["SHARED_VOLUME_ROOT"] == str(source.resolve())
    assert env["OSII_ROOT"] == str((runtime / ".osii").resolve())
    assert env["UPLOAD_ORIGINALS_ROOT"] == str((runtime / "uploads").resolve())
    assert env["OSII_SOURCE_KIND"] == "shared"
    assert not (source / ".osii").exists()


def test_shared_drive_environment_does_not_create_missing_source(monkeypatch, tmp_path):
    source = tmp_path / "offline-share"
    monkeypatch.setattr(DEV_STACK, "load_dotenv", lambda _path: {})
    monkeypatch.setenv("OSII_SOURCE_DIR", str(source))

    with pytest.raises(RuntimeError, match="Connect or mount the shared drive"):
        DEV_STACK.build_environment(core_only=True)

    assert not source.exists()
