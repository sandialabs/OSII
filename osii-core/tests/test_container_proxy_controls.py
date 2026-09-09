from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROXY_VARIABLES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "FTP_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "ftp_proxy",
    "all_proxy",
)


def _make_command(target: str, *, disable_proxies: bool) -> str:
    if shutil.which("make") is None:
        pytest.skip("Make is not installed on this platform")
    result = subprocess.run(
        [
            "make",
            "-n",
            target,
            f"DISABLE_CONTAINER_PROXIES={'true' if disable_proxies else 'false'}",
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def test_make_build_disables_and_removes_proxy_environment() -> None:
    command = _make_command("build", disable_proxies=True)

    assert "--podman-build-args=" in command
    assert "--http-proxy=false" in command
    for variable in PROXY_VARIABLES:
        assert f"--env {variable}=" in command
        assert f"--unsetenv {variable}" in command

    assert "NO_PROXY=" not in command
    assert "SSL_CERT_FILE=" not in command
    assert "REQUESTS_CA_BUNDLE=" not in command


def test_make_run_disables_proxy_injection_without_build_options() -> None:
    command = _make_command("run", disable_proxies=True)

    assert "--podman-run-args=" in command
    assert "--http-proxy=false" in command
    assert "--unsetenv" not in command
    for variable in PROXY_VARIABLES:
        assert f"--env {variable}=" in command


def test_make_defaults_to_inherited_proxy_behavior() -> None:
    assert "--podman-build-args=" not in _make_command("build", disable_proxies=False)
    assert "--podman-run-args=" not in _make_command("run", disable_proxies=False)


def test_powershell_launcher_has_matching_proxy_controls() -> None:
    launcher = (REPOSITORY_ROOT / "scripts" / "osii.ps1").read_text(encoding="utf-8")

    assert "[switch]$DisableContainerProxies" in launcher
    assert 'if ($Runtime -ne "Podman")' in launcher
    assert '"--podman-build-args=$($BuildOptions -join \' \')"' in launcher
    assert '"--podman-run-args=$($RunOptions -join \' \')"' in launcher
    for variable in PROXY_VARIABLES:
        assert f'"{variable}"' in launcher
