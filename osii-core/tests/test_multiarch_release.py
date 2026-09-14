from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "publish_multiarch.py"


def dry_run(*extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--image-prefix", "quay.example.org/team/osii",
            "--image-tag", "1.2.3",
            "--base-image", "quay.example.org/dice/rhel9",
            "--dry-run",
            *extra,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )


def test_dry_run_builds_four_images_for_both_linux_architectures() -> None:
    output = dry_run().stdout
    assert output.count("podman build --platform linux/amd64") == 4
    assert output.count("podman build --platform linux/arm64") == 4
    assert output.count("podman manifest push --all") == 4
    assert "osii-core:1.2.3-amd64" in output
    assert "osii-tesseract:1.2.3-arm64" in output


def test_direct_mode_removes_proxy_variables_from_built_images() -> None:
    output = dry_run("--disable-container-proxies").stdout
    assert "--http-proxy=false" in output
    assert "--unsetenv HTTP_PROXY" in output
    assert "--unsetenv https_proxy" in output


def test_latest_tag_is_rejected() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--image-prefix", "quay.example.org/team/osii",
            "--image-tag", "latest",
            "--base-image", "quay.example.org/dice/rhel9",
            "--dry-run",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "immutable release tag" in result.stderr
