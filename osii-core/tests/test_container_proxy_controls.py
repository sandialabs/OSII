from __future__ import annotations

import shutil
import subprocess
import sys
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
CA_AWARE_DOCKERFILES = (
    "osii-core/Dockerfile",
    "osii-core/services/baseline-processors/Dockerfile",
    "osii-dashboard/dashboard/Dockerfile",
    "osii-mcp/Dockerfile",
    "osii-toolbox/minilm-embedding-service/Dockerfile",
    "osii-toolbox/model2vec-embedder/Dockerfile",
    "osii-toolbox/osii-tesseract/Dockerfile",
    "osii-toolbox/tabular-dataset-processors/Dockerfile",
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


def test_make_passes_ca_bundle_as_cache_safe_build_secret(tmp_path: Path) -> None:
    if shutil.which("make") is None:
        pytest.skip("Make is not installed on this platform")
    bundle = tmp_path / "local trust.pem"
    bundle.write_text("test input used only to inspect make output", encoding="utf-8")

    result = subprocess.run(
        ["make", "-n", "build", f"OSII_CA_BUNDLE={bundle}"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert f'--secret=id=osii_ca_bundle,src="{bundle}"' in result.stdout
    assert "--mount=type=secret,id=osii_ca_bundle" in result.stdout
    assert "--build-arg OSII_CA_BUNDLE_SHA256=" in result.stdout
    assert "--env REQUESTS_CA_BUNDLE=/etc/pki/tls/certs/ca-bundle.crt" in result.stdout
    assert "--env UV_NATIVE_TLS=true" in result.stdout
    assert "--env NODE_EXTRA_CA_CERTS=" in result.stdout
    assert "COPY" not in result.stdout


def test_all_osii_dockerfiles_install_only_the_explicit_ca_secret() -> None:
    for relative_path in CA_AWARE_DOCKERFILES:
        contents = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
        assert "ARG OSII_CA_BUNDLE_SHA256=none" in contents
        assert "[ -f /run/secrets/osii_ca_bundle ]" in contents
        assert "/etc/pki/ca-trust/source/anchors/osii-local-ca-bundle.pem" in contents
        assert "update-ca-trust" in contents


def test_ca_validator_rejects_private_keys(tmp_path: Path) -> None:
    bundle = tmp_path / "unsafe.pem"
    bundle.write_text(
        "-----BEGIN PRIVATE KEY-----\nnot-a-key\n-----END PRIVATE KEY-----\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "scripts/validate_ca_bundle.py", str(bundle)],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "contains a private key" in result.stderr


def test_powershell_launcher_has_matching_ca_secret_support() -> None:
    launcher = (REPOSITORY_ROOT / "scripts" / "osii.ps1").read_text(encoding="utf-8")

    assert "[string]$CaBundle" in launcher
    assert "Test-OsiiCaBundle" in launcher
    assert "--secret=id=osii_ca_bundle" in launcher
    assert "--mount=type=secret,id=osii_ca_bundle" in launcher
    assert "OSII_CA_BUNDLE_SHA256=" in launcher


def test_make_and_powershell_offer_mounted_shared_drive_launchers() -> None:
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    launcher = (REPOSITORY_ROOT / "scripts" / "osii.ps1").read_text(encoding="utf-8")

    assert "dev-shared:" in makefile
    assert "run-shared:" in makefile
    assert "SHARED_DRIVE_PATH" in makefile
    assert "OSII_SOURCE_KIND=shared" in makefile
    assert '"dev-shared"' in launcher
    assert '"run-shared"' in launcher
    assert "[string]$SourceDir" in launcher
    assert '$env:OSII_SOURCE_KIND = "shared"' in launcher
