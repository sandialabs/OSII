"""Build-time assets only. Nothing in this script runs on an installed workstation."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import urllib.request
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "osii-desktop" / "resources"


def verified_download(url: str, sha256: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "OSII-release-builder"})
    with urllib.request.urlopen(request, timeout=180) as response:
        content = response.read()
    if hashlib.sha256(content).hexdigest() != sha256:
        raise RuntimeError("Build dependency checksum mismatch: " + url)
    return content


def prepare_ocr() -> None:
    if os.name != "nt":
        raise RuntimeError("The Windows OCR payload must be prepared on Windows.")
    lock = json.loads((ROOT / "osii-desktop" / "ocr-lock.json").read_text())
    archive = ZipFile(BytesIO(verified_download(lock["url"], lock["sha256"])))
    installer = archive.read(lock["installer"])
    if hashlib.sha256(installer).hexdigest() != lock["installer_sha256"]:
        raise RuntimeError("Tesseract installer checksum mismatch")
    output = PAYLOAD / "ocr"
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="osii-ocr-build-") as directory:
        temporary = Path(directory)
        executable = temporary / "tesseract-setup.exe"
        executable.write_bytes(installer)
        sevenzip = shutil.which("7z") or str(Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "7-Zip" / "7z.exe")
        subprocess.run([sevenzip, "x", str(executable), "-o" + str(temporary / "extracted"), "-y"], check=True, stdout=subprocess.DEVNULL)
        extracted = temporary / "extracted"
        engine = next(extracted.rglob("tesseract.exe"), None)
        if engine is None:
            raise RuntimeError("The verified Tesseract archive contains no engine")
        shutil.copy2(engine, output / "tesseract.exe")
        for library in engine.parent.glob("*.dll"):
            shutil.copy2(library, output / library.name)
        for notice in engine.parent.glob("*LICENSE*"):
            if notice.is_file():
                shutil.copy2(notice, output / notice.name)
        # Upstream runtime notices may be in a subdirectory.
        for name in ("doc", "licenses"):
            if (engine.parent / name).is_dir():
                shutil.copytree(engine.parent / name, output / name)
    language_dir = output / "tessdata"
    language_dir.mkdir()
    def language(item):
        name, digest = item
        url = f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{lock['language_commit']}/{name}.traineddata"
        (language_dir / (name + ".traineddata")).write_bytes(verified_download(url, digest))
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(language, lock["languages"].items()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ocr", action="store_true", help="Fetch and verify the pinned Windows OCR build assets")
    parser.add_argument("--dashboard", action="store_true", help="Include the already-built dashboard")
    args = parser.parse_args()
    PAYLOAD.mkdir(parents=True, exist_ok=True)
    version = tomllib.loads((ROOT / "osii-core" / "pyproject.toml").read_text())["project"]["version"]
    (PAYLOAD / "release.json").write_text(json.dumps({"version": version, "target": "windows-x64", "storage": "sidecar"}) + "\n")
    if args.ocr:
        prepare_ocr()
    if args.dashboard:
        dashboard = ROOT / "osii-dashboard" / "dashboard" / "dist"
        if not (dashboard / "index.html").is_file():
            raise RuntimeError("Build the dashboard before preparing its release assets")
        shutil.copytree(dashboard, PAYLOAD / "dashboard", dirs_exist_ok=True)


if __name__ == "__main__":
    main()
