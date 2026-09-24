from __future__ import annotations

import os
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
    "osii-toolbox/osii-tesseract/Dockerfile",
    "osii-toolbox/tabular-dataset-processors/Dockerfile",
)


@pytest.fixture
def dotenv_checkout(tmp_path: Path) -> Path:
    if shutil.which("uv") is None:
        pytest.skip("uv is required for dotenv loading")
    shutil.copyfile(REPOSITORY_ROOT / "Makefile", tmp_path / "Makefile")
    (tmp_path / "scripts").mkdir()
    for name in ("publish_multiarch.py", "osii.ps1"):
        shutil.copyfile(REPOSITORY_ROOT / "scripts" / name, tmp_path / "scripts" / name)
    (tmp_path / ".env").write_text(
        '# Workstation release defaults\n'
        'OSII_IMAGE_PREFIX="quay.example.org/team/osii"\n'
        'OSII_IMAGE_TAG="1.2.3"\n'
        'OSII_BASE_IMAGE="quay.example.org/approved/rhel9"\n'
        'OSII_PYTHON_VERSION=3.12\n'
        'OSII_CA_BUNDLE=\n'
        'DISABLE_CONTAINER_PROXIES=true\n'
        'OSII_TESSERACT_SOURCE_URL="https://artifacts.example/tesseract.tar.gz"\n',
        encoding="utf-8",
    )
    return tmp_path


def dotenv_environment() -> dict[str, str]:
    return {key: value for key, value in os.environ.items()
            if not key.startswith("OSII_") and key != "DISABLE_CONTAINER_PROXIES"}


@pytest.mark.parametrize("shell_tag,command_tag,expected", [
    (None, None, "1.2.3"), ("2.0.0", None, "2.0.0"), ("2.0.0", "3.0.0", "3.0.0"),
])
def test_make_loads_dotenv_with_explicit_overrides(
    dotenv_checkout: Path, shell_tag: str | None, command_tag: str | None, expected: str,
) -> None:
    if shutil.which("make") is None:
        pytest.skip("Make is not installed")
    env = dotenv_environment()
    if shell_tag:
        env["OSII_IMAGE_TAG"] = shell_tag
    command = ["make", "publish-multiarch", "DRY_RUN=true"]
    if command_tag:
        command.append(f"OSII_IMAGE_TAG={command_tag}")
    result = subprocess.run(command, cwd=dotenv_checkout, env=env,
                            text=True, capture_output=True, check=True)
    assert f"quay.example.org/team/osii-core:{expected}-amd64" in result.stdout
    assert "OSII_TESSERACT_SOURCE_URL=https://artifacts.example/tesseract.tar.gz" in result.stdout
    assert "--http-proxy=false" in result.stdout


def test_make_dotenv_quoted_ca_path_and_dry_run(dotenv_checkout: Path) -> None:
    if shutil.which("make") is None:
        pytest.skip("Make is not installed")
    bundle = dotenv_checkout / "corporate roots.pem"
    bundle.write_text("dry-run certificate placeholder", encoding="utf-8")
    config = dotenv_checkout / ".env"
    config.write_text(config.read_text(encoding="utf-8").replace(
        "OSII_CA_BUNDLE=\n", f'OSII_CA_BUNDLE="{bundle.as_posix()}"\n'), encoding="utf-8")
    result = subprocess.run(["make", "-n", "build"], cwd=dotenv_checkout,
                            env=dotenv_environment(), text=True, capture_output=True, check=True)
    assert f'src="{bundle}"' in result.stdout
    assert "--http-proxy=false" in result.stdout


@pytest.mark.parametrize("shell_tag,command_tag,expected", [
    (None, None, "1.2.3"), ("2.0.0", None, "2.0.0"), ("2.0.0", "3.0.0", "3.0.0"),
])
def test_powershell_loads_dotenv_with_explicit_overrides(
    dotenv_checkout: Path, shell_tag: str | None, command_tag: str | None, expected: str,
) -> None:
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is not installed")
    env = dotenv_environment()
    if shell_tag:
        env["OSII_IMAGE_TAG"] = shell_tag
    command = [powershell, "-NoProfile", "-File", str(dotenv_checkout / "scripts/osii.ps1"),
               "publish-multiarch", "-DryRun"]
    if command_tag:
        command += ["-ImageTag", command_tag]
    result = subprocess.run(command, cwd=dotenv_checkout.parent, env=env,
                            text=True, capture_output=True, check=True)
    assert f"quay.example.org/team/osii-core:{expected}-amd64" in result.stdout
    assert "OSII_TESSERACT_SOURCE_URL=https://artifacts.example/tesseract.tar.gz" in result.stdout
    assert "--http-proxy=false" in result.stdout


def test_powershell_reloads_dotenv_and_restores_shell(dotenv_checkout: Path) -> None:
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is not installed")
    result = subprocess.run([
        powershell, "-NoProfile", "-Command",
        "$ErrorActionPreference = 'Stop'; "
        "& ./scripts/osii.ps1 publish-multiarch -DryRun -DisableContainerProxies:$false; "
        "if (Test-Path Env:OSII_IMAGE_TAG) { throw 'Leaked image tag' }; "
        "(Get-Content .env -Raw).Replace('1.2.3', '1.2.4') | Set-Content .env; "
        "& ./scripts/osii.ps1 publish-multiarch -DryRun -DisableContainerProxies:$false",
    ], cwd=dotenv_checkout, env=dotenv_environment(), text=True, capture_output=True, check=True)
    assert "osii-core:1.2.3-amd64" in result.stdout
    assert "osii-core:1.2.4-amd64" in result.stdout
    assert "--http-proxy=false" not in result.stdout


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
    assert "--env REQUESTS_CA_BUNDLE=/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem" in result.stdout
    assert "--env UV_SYSTEM_CERTS=true" in result.stdout
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
    assert "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem" in launcher


def test_build_launchers_clean_podman_secret_artifacts() -> None:
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    launcher = (REPOSITORY_ROOT / "scripts" / "osii.ps1").read_text(encoding="utf-8")

    assert 'find "$(CURDIR)" -type f -name "podman-build-secret-*" -delete' in makefile
    assert 'Get-ChildItem -LiteralPath $RepositoryRoot -Filter "podman-build-secret-*"' in launcher
    assert "Remove-Item -Force" in launcher


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


def test_make_and_powershell_start_container_stacks_detached() -> None:
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    launcher = (REPOSITORY_ROOT / "scripts" / "osii.ps1").read_text(encoding="utf-8")

    assert makefile.count("up -d --no-build --pull missing") == 3
    assert launcher.count('Invoke-OsiiCompose @("up", "-d", "--no-build"') == 2


def test_toolbox_images_are_optional_and_have_cross_platform_helpers() -> None:
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    launcher = (REPOSITORY_ROOT / "scripts" / "osii.ps1").read_text(encoding="utf-8")
    compose = (REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert "toolbox-build:" in makefile
    assert "toolbox-push:" in makefile
    assert "toolbox-run:" in makefile
    assert "toolbox-publish-multiarch:" in makefile
    assert '"toolbox-build"' in launcher
    assert '"toolbox-push"' in launcher
    assert '"toolbox-run"' in launcher
    assert '"toolbox-publish-multiarch"' in launcher
    assert compose.count('profiles: ["toolbox"]') == 5
    assert "readable-wiki-enricher" in compose
    assert "concept-entity-wiki-enricher" in compose

    make_run = _make_command("run", disable_proxies=False)
    assert " tesseract " in make_run
    assert "tesseract-opencv" not in make_run
