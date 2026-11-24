"""Build and validate native Standalone packages on the maintainer's machine."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(arguments: list[str], *, directory: Path = ROOT, environment=None) -> None:
    subprocess.run(arguments, cwd=directory, env=environment, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and validate OSII's complete offline desktop package")
    parser.add_argument("--pilot", action="store_true", help="Allow an explicitly unsigned pilot build")
    args = parser.parse_args()
    mac = sys.platform == "darwin" and platform.machine() == "arm64"
    windows = os.name == "nt" and platform.machine().lower() in {"amd64", "x86_64"}
    if not (windows or mac):
        parser.error("Build the native package on Windows x64 or Apple Silicon, or use the Standalone GitHub workflows.")
    if mac and not args.pilot:
        parser.error("The macOS build currently supports --pilot. Developer ID signing and notarization are not configured.")
    if sys.version_info[:2] != (3, 12):
        parser.error("Use the locked Python 3.12 build environment documented in docs/operations/standalone.md.")
    node, npm = shutil.which("node"), shutil.which("npm")
    if not node or not npm:
        parser.error("The build machine needs Node.js 22.18+ and npm. Installed OSII users do not need them.")
    # Execute npm's JS CLI with Node directly; no cmd.exe parsing of paths.
    npm_cli = Path(npm).resolve() if mac else Path(npm).parent / "node_modules" / "npm" / "bin" / "npm-cli.js"
    if not npm_cli.is_file():
        parser.error("Cannot locate npm's CLI. Use the standard Node distribution or GitHub CI.")
    dashboard = ROOT / "osii-dashboard" / "dashboard"
    desktop = ROOT / "osii-desktop"
    for directory in (dashboard, desktop):
        run([node, str(npm_cli), "ci", "--no-audit", "--no-fund"], directory=directory)
        run([node, str(npm_cli), "test"], directory=directory)
    run([node, str(npm_cli), "run", "build"], directory=dashboard)
    run([sys.executable, "-m", "pytest", "osii-core/tests/test_library_lock.py", "osii-core/tests/test_desktop.py", "-q"])
    run([sys.executable, "-m", "pytest", "osii-core/services", "--import-mode=importlib", "-q"])
    run([sys.executable, "scripts/prepare_standalone.py", "--ocr", "--embedding", "--dashboard"])
    run([sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "--distpath", "osii-desktop/resources/runtime", "osii-desktop/runtime.spec"])
    executable = desktop / "resources" / "runtime" / "osii-runtime" / ("osii-runtime" if mac else "osii-runtime.exe")
    clean = os.environ.copy()
    clean["PATH"] = "/usr/bin:/bin" if mac else str(Path(os.environ["SystemRoot"]) / "System32")
    clean.pop("PYTHONPATH", None)
    clean.pop("PYTHONHOME", None)
    for _ in range(2):
        run([str(executable), "self-test"], environment=clean)
    run([sys.executable, "scripts/check_standalone.py", "--runtime", str(executable)])
    release = ROOT / "release" / "standalone"
    if mac:
        installer = release / "OSII-Standalone-macOS-arm64.dmg"
        run([node, str(npm_cli), "run", "package:mac-pilot"], directory=desktop)
        run(["/bin/bash", "scripts/check_standalone_macos.sh", str(installer)])
        checksums, validation = "SHA256SUMS-macOS.txt", "validation-macOS.json"
    else:
        installer = release / "OSII-Standalone-Setup.exe"
        run([node, str(npm_cli), "run", "package:pilot" if args.pilot else "package:windows"], directory=desktop)
        powershell = shutil.which("pwsh") or str(Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe")
        run([powershell, "-NoProfile", "-File", "scripts/check_standalone_installer.ps1", *([] if args.pilot else ["-RequireSignature"])])
        checksums, validation = "SHA256SUMS.txt", "validation.json"
    with installer.open("rb") as package:
        digest = hashlib.file_digest(package, "sha256").hexdigest()
    (release / checksums).write_text(f"{digest}  {installer.name}\n", encoding="utf-8")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    results = ({"developerIdSigned": False, "notarized": False, "offlineSemanticSearch": "passed", "target": "macos-arm64"}
               if mac else {"signed": not args.pilot, "cleanWindowsAcceptance": "pending"})
    (release / validation).write_text(json.dumps({**results, "commit": commit, "installerBytes": installer.stat().st_size}, indent=2) + "\n")
    label = "Validated pilot installer: " if args.pilot else "Signed installer: "
    print(label + str(installer))
    if windows:
        print("Clean standard-user Windows acceptance remains required before broad release.")


if __name__ == "__main__":
    main()
