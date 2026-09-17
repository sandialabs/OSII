#!/usr/bin/env python3
"""Collect locally available OSII container images for an offline workstation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from publish_multiarch import RELEASE_IMAGES, TOOLBOX_IMAGES


RELEASE_NAMES = tuple(name for name, _, _ in RELEASE_IMAGES)
TOOLBOX_NAMES = tuple(name for name, _, _ in TOOLBOX_IMAGES)
ARCHIVE_NAME = "osii-images.tar"
MANIFEST_NAME = "manifest.json"


def image_references(prefix: str, tag: str, toolbox: list[str]) -> list[str]:
    if not prefix or not tag or any(character.isspace() for character in prefix + tag):
        raise ValueError("Provide a nonempty image prefix and tag without whitespace.")
    names = (*RELEASE_NAMES, *(name for name in TOOLBOX_NAMES if name in toolbox))
    return [f"{prefix.rstrip('/')}-{name}:{tag}" for name in names]


def inspect_image(runtime: str, reference: str) -> dict[str, str]:
    result = subprocess.run(
        [runtime, "image", "inspect", reference], text=True, capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"Image is not available locally: {reference}. Pull or build it first, "
            f"or use --pull on a connected computer. {result.stderr.strip()}"
        )
    try:
        image = json.loads(result.stdout)[0]
        platform = f"{image['Os']}/{image['Architecture']}"
        identifier = str(image["Id"])
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Could not inspect image {reference}.") from exc
    return {"reference": reference, "id": identifier, "platform": platform}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def export_images(
    *, runtime: str, prefix: str, tag: str, toolbox: list[str],
    output_dir: Path, pull: bool = False, platform: str | None = None,
) -> dict:
    references = image_references(prefix, tag, toolbox)
    archive = output_dir / ARCHIVE_NAME
    manifest_path = output_dir / MANIFEST_NAME
    if archive.exists() or manifest_path.exists():
        raise FileExistsError(
            f"{output_dir} already contains an OSII image export. Choose a new directory."
        )

    if pull:
        for reference in references:
            print(f"Pulling {reference}", flush=True)
            command = [runtime, "pull"]
            if platform:
                command += ["--platform", platform]
            subprocess.run([*command, reference], check=True)
    images = [inspect_image(runtime, reference) for reference in references]
    platforms = {image["platform"] for image in images}
    if len(platforms) != 1:
        raise ValueError(
            "Images have different platforms; export one architecture at a time: "
            + ", ".join(sorted(platforms))
        )
    selected_platform = platforms.pop()
    if platform and selected_platform != platform:
        raise ValueError(
            f"The local images are {selected_platform}, not {platform}. "
            "Use --pull to fetch the requested architecture on a connected computer."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=".osii-images-", suffix=".tar", dir=output_dir, delete=False,
    ) as handle:
        temporary = Path(handle.name)
    try:
        command = [runtime, "save"]
        if runtime == "podman":
            command += ["--multi-image-archive", "--format", "docker-archive"]
        command += ["--output", str(temporary), *references]
        print(f"Saving {len(references)} images to {archive} ({selected_platform})", flush=True)
        subprocess.run(command, check=True)
        if temporary.stat().st_size == 0:
            raise RuntimeError("The container runtime created an empty archive.")
        manifest = {
            "version": 1,
            "archive": ARCHIVE_NAME,
            "sha256": file_sha256(temporary),
            "images": images,
        }
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix=".osii-manifest-", suffix=".json",
            dir=output_dir, delete=False,
        ) as handle:
            temporary_manifest = Path(handle.name)
            json.dump(manifest, handle, indent=2)
            handle.write("\n")
        try:
            if archive.exists() or manifest_path.exists():
                raise FileExistsError("An OSII export appeared while this export was running.")
            os.replace(temporary, archive)
            try:
                os.replace(temporary_manifest, manifest_path)
            except OSError:
                archive.unlink(missing_ok=True)
                raise
        finally:
            temporary_manifest.unlink(missing_ok=True)
        return manifest
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--image-prefix", default=os.getenv("OSII_IMAGE_PREFIX", "localhost/osii"))
    parser.add_argument("--image-tag", default=os.getenv("OSII_IMAGE_TAG", "latest"))
    parser.add_argument("--runtime", choices=("podman", "docker"), default="podman")
    parser.add_argument("--platform", choices=("linux/amd64", "linux/arm64"))
    parser.add_argument("--toolbox", choices=TOOLBOX_NAMES, action="append", default=[])
    parser.add_argument("--pull", action="store_true", help="Pull the selected tags before exporting (requires network access).")
    args = parser.parse_args()
    try:
        manifest = export_images(
            runtime=args.runtime, prefix=args.image_prefix, tag=args.image_tag,
            toolbox=args.toolbox, output_dir=args.output_dir.expanduser(),
            pull=args.pull, platform=args.platform,
        )
    except (FileExistsError, OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Image export failed: {exc}\n")
    print(f"Archive SHA-256: {manifest['sha256']}")
    print("Transfer the entire output directory. On the offline computer, run:")
    print(f"  {args.runtime} load --input {args.output_dir / ARCHIVE_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
