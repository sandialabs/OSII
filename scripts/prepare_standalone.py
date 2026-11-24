"""Build-time assets only. Nothing in this script runs on an installed workstation."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
from importlib.metadata import distributions
from io import BytesIO
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import urllib.request
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "osii-desktop" / "resources"
MAC_ARM64 = sys.platform == "darwin" and platform.machine() == "arm64"


def verified_download(url: str, sha256: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "OSII-release-builder"})
    with urllib.request.urlopen(request, timeout=180) as response:
        content = response.read()
    if hashlib.sha256(content).hexdigest() != sha256:
        raise RuntimeError("Build dependency checksum mismatch: " + url)
    return content


def prepare_ocr() -> None:
    if MAC_ARM64:
        prepare_macos_ocr()
        return
    if os.name != "nt":
        raise RuntimeError("Build the OCR payload on Windows x64 or Apple Silicon.")
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
        # `tesseract ... tsv` loads tessdata/configs/tsv. Language weights
        # alone can return exit code zero but plain text instead of TSV.
        for name in ("configs", "tessconfigs"):
            source = engine.parent / "tessdata" / name
            if source.is_dir():
                shutil.copytree(source, output / "tessdata" / name)
        if not (output / "tessdata" / "configs" / "tsv").is_file():
            raise RuntimeError("The OCR payload is missing its required TSV configuration")
        if (engine.parent / "tessdata" / "osd.traineddata").is_file():
            shutil.copy2(engine.parent / "tessdata" / "osd.traineddata", output / "tessdata" / "osd.traineddata")
        for notice in engine.parent.glob("*LICENSE*"):
            if notice.is_file():
                shutil.copy2(notice, output / notice.name)
        # Upstream runtime notices may be in a subdirectory.
        for name in ("doc", "licenses"):
            if (engine.parent / name).is_dir():
                shutil.copytree(engine.parent / name, output / name)
    write_ocr_languages(output / "tessdata", lock)


def write_ocr_languages(language_dir: Path, lock: dict) -> None:
    language_dir.mkdir(exist_ok=True)
    def language(item):
        name, digest = item
        url = f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{lock['language_commit']}/{name}.traineddata"
        (language_dir / (name + ".traineddata")).write_bytes(verified_download(url, digest))
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(language, lock["languages"].items()))


def prepare_macos_ocr() -> None:
    lock = json.loads((ROOT / "osii-desktop" / "macos-ocr-lock.json").read_text())
    languages = json.loads((ROOT / "osii-desktop" / "ocr-lock.json").read_text())
    languages["languages"]["osd"] = "9cf5d576fcc47564f11265841e5ca839001e7e6f38ff7f7aacf46d15a96b00ff"
    output = PAYLOAD / "ocr"
    with tempfile.TemporaryDirectory(prefix="ocr-", dir=PAYLOAD) as directory:
        temporary = Path(directory)
        prefix = temporary / "install"
        staged = temporary / "payload"
        staged.mkdir()
        tesseract_dependencies = temporary / "tesseract-dependencies.cmake"
        tesseract_dependencies.write_text("find_package(ZLIB REQUIRED)\n", encoding="utf-8")
        # The processor renders inputs to PNG. Leptonica also reads its built-in TIFF fonts.
        configurations = {
            "libpng": ["-DPNG_SHARED=OFF", "-DPNG_FRAMEWORK=OFF", "-DPNG_TESTS=OFF", "-DPNG_TOOLS=OFF"],
            "libtiff": ["-Dtiff-tools=OFF", "-Dtiff-tests=OFF", "-Dtiff-contrib=OFF", "-Dtiff-docs=OFF",
                        "-Djpeg=OFF", "-Djbig=OFF", "-Dlzma=OFF", "-Dzstd=OFF", "-Dwebp=OFF", "-Dlerc=OFF", "-Dlibdeflate=OFF"],
            "leptonica": ["-DENABLE_GIF=OFF", "-DENABLE_JPEG=OFF",
                          "-DENABLE_WEBP=OFF", "-DENABLE_OPENJPEG=OFF", "-DSTRICT_CONF=ON"],
            "tesseract": ["-DBUILD_TRAINING_TOOLS=OFF", "-DENABLE_NATIVE=OFF", "-DDISABLE_TIFF=ON",
                          "-DDISABLE_ARCHIVE=ON", "-DDISABLE_CURL=ON", "-DGRAPHICS_DISABLED=ON",
                          "-DCMAKE_PROJECT_tesseract_INCLUDE=" + str(tesseract_dependencies)],
        }
        for name, flags in configurations.items():
            dependency = lock[name]
            source_dir = temporary / name
            with tarfile.open(fileobj=BytesIO(verified_download(dependency["url"], dependency["sha256"]))) as archive:
                archive.extractall(source_dir, filter="data")
            source, = source_dir.iterdir()
            build = temporary / (name + "-build")
            subprocess.run([
                "cmake", "-S", str(source), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
                "-DCMAKE_OSX_ARCHITECTURES=arm64", "-DCMAKE_OSX_DEPLOYMENT_TARGET=15.0",
                "-DCMAKE_INSTALL_PREFIX=" + str(prefix), "-DCMAKE_PREFIX_PATH=" + str(prefix),
                "-DCMAKE_IGNORE_PREFIX_PATH=/opt/homebrew;/usr/local", "-DBUILD_SHARED_LIBS=OFF",
                "-DCMAKE_DISABLE_FIND_PACKAGE_PkgConfig=ON", *flags,
            ], check=True)
            subprocess.run(["cmake", "--build", str(build), "--parallel", str(min(8, os.cpu_count() or 1))], check=True)
            subprocess.run(["cmake", "--install", str(build)], check=True)
            shutil.copy2(source / dependency["license"], staged / ("LICENSE-" + name))
        engine = staged / "tesseract"
        shutil.copy2(prefix / "bin" / "tesseract", engine)
        libraries = subprocess.check_output(["otool", "-L", str(engine)], text=True).splitlines()[1:]
        if any(not row.strip().startswith(("/usr/lib/", "/System/Library/")) for row in libraries):
            raise RuntimeError("The macOS OCR binary has an external dependency: " + "\n".join(libraries))
        language_dir = staged / "tessdata"
        shutil.copytree(prefix / "share" / "tessdata", language_dir)
        write_ocr_languages(language_dir, languages)
        if not (language_dir / "configs" / "tsv").is_file():
            raise RuntimeError("The macOS OCR payload is missing its required TSV configuration")
        if output.exists():
            shutil.rmtree(output)
        staged.rename(output)


def windows_cpp_runtime() -> list[Path]:
    """Select the app-local redistributable DLLs from the Windows build tools."""
    filenames = ("msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll")
    installed = os.getenv("VCToolsRedistDir")
    if installed:
        candidates = list(Path(installed).glob("x64/Microsoft.VC*.CRT"))
    else:
        installer = Path(os.environ["ProgramFiles(x86)"]) / "Microsoft Visual Studio" / "Installer"
        vs_path = subprocess.check_output(
            [str(installer / "vswhere.exe"), "-latest", "-products", "*", "-utf8",
             "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
             "-property", "installationPath"], encoding="utf-8",
        ).strip()
        candidates = list((Path(vs_path) / "VC" / "Redist" / "MSVC").glob("*/x64/Microsoft.VC*.CRT"))
    candidates = [
        path for path in candidates
        if all((path / filename).is_file() for filename in filenames)
    ]
    if not candidates:
        raise RuntimeError("Install the Visual Studio C++ x64 build tools and redistributable files on the build machine.")
    newest = max(candidates, key=lambda path: tuple(
        int(part) for part in path.resolve().parents[1].name.split(".") if part.isdecimal()
    ))
    return [newest / filename for filename in filenames]


def prepare_embedding() -> None:
    if os.name != "nt" and not MAC_ARM64:
        raise RuntimeError("Build the embedding payload on Windows x64 or Apple Silicon.")
    lock = json.loads((ROOT / "osii-desktop" / "embedding-lock.json").read_text())
    windows_engine, model = lock["runtime"], lock["model"]
    engine = lock["macos_arm64"] if MAC_ARM64 else windows_engine
    output = PAYLOAD / "embedding"
    with tempfile.TemporaryDirectory(prefix="embedding-", dir=PAYLOAD) as directory:
        staged = Path(directory) / "payload"
        staged.mkdir()
        runtime_archive = BytesIO(verified_download(engine["url"], engine["sha256"]))
        redistributable_notice = ""
        if MAC_ARM64:
            with tarfile.open(fileobj=runtime_archive) as archive:
                archive.extractall(directory, filter="data")
            package, = (entry for entry in Path(directory).iterdir() if entry != staged)
            libraries = (library for library in package.glob("*.dylib")
                         if not library.name.endswith("-impl.dylib") or library.name == "libllama-server-impl.dylib")
            for binary in (package / "llama-server", *libraries):
                shutil.copy2(binary, staged / binary.name, follow_symlinks=False)
        else:
            with ZipFile(runtime_archive) as archive:
                files = {"llama-server.exe", "llama-server-impl.dll", "llama-common.dll",
                         "llama.dll", "mtmd.dll", "ggml.dll", "ggml-base.dll",
                         "libomp.dll", "LICENSE-LLVM-OpenMP"}
                files.update(name for name in archive.namelist() if name.startswith("ggml-cpu-") and name.endswith(".dll"))
                if "ggml-cpu-x64.dll" not in files:
                    raise RuntimeError("The verified archive is missing the generic Windows x64 CPU backend.")
                for name in files:
                    (staged / name).write_bytes(archive.read(name))
            dlls = windows_cpp_runtime()
            for dll in dlls:
                shutil.copy2(dll, staged / dll.name)
            redistributable_notice = (
                "Microsoft Visual C++ Redistributable DLLs from the build machine: " + dlls[0].parents[2].name + "\n"
                "https://learn.microsoft.com/cpp/windows/redistributing-visual-cpp-files\n"
            )
        (staged / "model.gguf").write_bytes(verified_download(model["url"], model["sha256"]))
        for name, entry in (("LICENSE-llama.cpp", windows_engine), ("LICENSE-EmbeddingGemma", model)):
            (staged / name).write_bytes(verified_download(entry["license_url"], entry["license_sha256"]))
        (staged / "NOTICE.txt").write_text(
            "EmbeddingGemma 2 by Google, under Apache 2.0.\n"
            "Source model: https://huggingface.co/google/embeddinggemma-2\n"
            "Text-only GGUF conversion and UD-Q4_K_XL quantization by Unsloth.\n"
            "Weights: " + model["url"] + "\nSHA-256: " + model["sha256"] + "\n"
            "llama.cpp runtime (CPU mode): " + engine["url"] + "\nSHA-256: " + engine["sha256"] + "\n"
            + redistributable_notice,
            encoding="utf-8",
        )
        if output.exists():
            shutil.rmtree(output)
        staged.rename(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ocr", action="store_true", help="Prepare and verify the pinned OCR build assets")
    parser.add_argument("--embedding", action="store_true", help="Prepare verified CPU model assets")
    parser.add_argument("--dashboard", action="store_true", help="Include the already-built dashboard")
    args = parser.parse_args()
    PAYLOAD.mkdir(parents=True, exist_ok=True)
    version = tomllib.loads((ROOT / "osii-core" / "pyproject.toml").read_text())["project"]["version"]
    for filename in (ROOT / "osii-desktop" / "package.json", ROOT / "osii-dashboard" / "dashboard" / "package.json"):
        if json.loads(filename.read_text())["version"] != version:
            raise RuntimeError("Release version mismatch: " + str(filename))
    target = "macos-arm64" if MAC_ARM64 else "windows-x64"
    (PAYLOAD / "release.json").write_text(json.dumps({"version": version, "target": target, "storage": "sidecar"}) + "\n")
    notices = ["OSII bundled Python dependencies\nBuild tools may also appear in this inventory.\n"]
    for distribution in sorted(distributions(), key=lambda item: item.metadata.get("Name", "").lower()):
        metadata = distribution.metadata
        notices.append(f"\n{'=' * 72}\n{metadata.get('Name', 'Unknown')} {distribution.version}\n")
        notices.append("License: " + str(metadata.get("License-Expression") or metadata.get("License") or "See dependency source and license files") + "\n")
        for file in distribution.files or []:
            if ".dist-info" in str(file) and any(part.lower().startswith(("license", "copying", "notice")) for part in file.parts):
                path = distribution.locate_file(file)
                if path.is_file():
                    notices.append(f"\n{file}\n" + path.read_text(encoding="utf-8", errors="replace") + "\n")
    (PAYLOAD / "THIRD_PARTY_NOTICES.txt").write_text("".join(notices), encoding="utf-8")
    if args.ocr:
        prepare_ocr()
    if args.embedding:
        prepare_embedding()
    if args.dashboard:
        dashboard = ROOT / "osii-dashboard" / "dashboard" / "dist"
        if not (dashboard / "index.html").is_file():
            raise RuntimeError("Build the dashboard before preparing its release assets")
        if (PAYLOAD / "dashboard").exists():
            shutil.rmtree(PAYLOAD / "dashboard")
        shutil.copytree(dashboard, PAYLOAD / "dashboard")


if __name__ == "__main__":
    main()
