#!/usr/bin/env python3
"""Build and publish OSII's release images for Linux AMD64 and ARM64."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shlex
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RELEASE_IMAGES = (
    ("core", "osii-core/Dockerfile", "."),
    ("dashboard", "osii-dashboard/dashboard/Dockerfile", "osii-dashboard/dashboard"),
    ("baseline-processors", "osii-core/services/baseline-processors/Dockerfile", "."),
    ("tesseract", "osii-toolbox/osii-tesseract/Dockerfile", "."),
)
PROXY_NAMES = (
    "HTTP_PROXY", "HTTPS_PROXY", "FTP_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "ftp_proxy", "all_proxy",
)
CERTIFICATE_ENV = {
    "SSL_CERT_FILE": "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",
    "REQUESTS_CA_BUNDLE": "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",
    "CURL_CA_BUNDLE": "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",
    "PIP_CERT": "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",
    "UV_SYSTEM_CERTS": "true",
    "NODE_EXTRA_CA_CERTS": "/etc/pki/ca-trust/source/anchors/osii-local-ca-bundle.pem",
}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Build, push, and publish multi-architecture OSII images."
    )
    result.add_argument("--image-prefix", required=True)
    result.add_argument("--image-tag", required=True)
    result.add_argument("--base-image", required=True)
    result.add_argument("--python-version", default="3.12")
    result.add_argument(
        "--platforms", default="linux/amd64,linux/arm64",
        help="Comma-separated Linux platforms (default: linux/amd64,linux/arm64)",
    )
    result.add_argument("--ca-bundle", type=Path)
    result.add_argument("--disable-container-proxies", action="store_true")
    result.add_argument("--dry-run", action="store_true")
    return result


def run(command: list[str], *, dry_run: bool) -> None:
    print("+ " + shlex.join(command), flush=True)
    if not dry_run:
        subprocess.run(command, check=True)


def architecture(platform: str) -> str:
    parts = platform.split("/")
    if len(parts) < 2 or parts[0] != "linux" or not parts[1]:
        raise ValueError(f"Unsupported platform {platform!r}; use linux/ARCH.")
    return parts[1]


def certificate_options(bundle: Path | None) -> list[str]:
    if bundle is None:
        return []
    resolved = bundle.expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"CA bundle is not a readable file: {resolved}")
    subprocess.run(
        [sys.executable, "scripts/validate_ca_bundle.py", str(resolved)], check=True
    )
    digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
    options = [
        "--secret", f"id=osii_ca_bundle,src={resolved}",
        "--mount", "type=secret,id=osii_ca_bundle",
        "--build-arg", f"OSII_CA_BUNDLE_SHA256={digest}",
    ]
    for name, value in CERTIFICATE_ENV.items():
        options.extend(("--env", f"{name}={value}"))
    return options


def proxy_options(disabled: bool) -> list[str]:
    if not disabled:
        return []
    options = ["--http-proxy=false"]
    for name in PROXY_NAMES:
        options.extend(("--env", f"{name}=", "--unsetenv", name))
    return options


def main() -> int:
    args = parser().parse_args()
    os.chdir(REPOSITORY_ROOT)
    prefix = args.image_prefix.rstrip("/")
    if prefix.startswith("localhost/"):
        raise SystemExit("Use a registry image prefix, not localhost/.")
    if args.image_tag == "latest":
        raise SystemExit("Use an immutable release tag instead of latest.")
    platforms = tuple(item.strip() for item in args.platforms.split(",") if item.strip())
    if not platforms:
        raise SystemExit("At least one platform is required.")
    try:
        architectures = tuple(architecture(item) for item in platforms)
        if len(set(architectures)) != len(architectures):
            raise ValueError("Each requested platform must have a distinct architecture.")
        common_options = certificate_options(args.ca_bundle)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    common_options += proxy_options(args.disable_container_proxies)

    if not args.dry_run:
        run(["podman", "info"], dry_run=False)

    published: dict[str, list[str]] = {}
    for image_name, dockerfile, context in RELEASE_IMAGES:
        target = f"{prefix}-{image_name}:{args.image_tag}"
        published[target] = []
        for platform, arch in zip(platforms, architectures, strict=True):
            arch_target = f"{target}-{arch}"
            command = [
                "podman", "build", "--platform", platform,
                "--file", dockerfile, "--tag", arch_target,
                "--build-arg", f"OSII_VERSION={args.image_tag}",
                "--build-arg", f"OSII_BASE_IMAGE={args.base_image}",
                "--build-arg", f"OSII_PYTHON_VERSION={args.python_version}",
                *common_options,
            ]
            for variable in (
                "OSII_TESSERACT_SOURCE_URL", "OSII_LEPTONICA_SOURCE_URL",
                "OSII_TESSDATA_BASE_URL",
            ):
                if value := os.environ.get(variable):
                    command.extend(("--build-arg", f"{variable}={value}"))
            command.append(context)
            run(command, dry_run=args.dry_run)
            run(["podman", "push", arch_target], dry_run=args.dry_run)
            published[target].append(arch_target)

    for target, members in published.items():
        if not args.dry_run:
            subprocess.run(
                ["podman", "manifest", "rm", target],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            print("+ " + shlex.join(["podman", "manifest", "rm", target]) + "  # if present")
        run(["podman", "manifest", "create", target], dry_run=args.dry_run)
        for member in members:
            run(
                ["podman", "manifest", "add", target, f"docker://{member}"],
                dry_run=args.dry_run,
            )
        run(["podman", "manifest", "inspect", target], dry_run=args.dry_run)
        run(
            ["podman", "manifest", "push", "--all", target, f"docker://{target}"],
            dry_run=args.dry_run,
        )

    print("Published multi-architecture OSII release:")
    for target in published:
        print(f"  {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
