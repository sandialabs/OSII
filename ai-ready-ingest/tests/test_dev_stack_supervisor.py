from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request


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
            "OSII_TESSERACT_PORT": "18080",
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
        assert {item["id"] for item in payload["services"]} == {"tesseract", "tika"}
    finally:
        supervisor.close()


def test_supervisor_rejects_unknown_services_and_actions():
    supervisor = DEV_STACK.CapabilitySupervisor(
        services=[],
        env={"OSII_TESSERACT_PORT": "18080", "OSII_TIKA_PORT": "19998"},
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
