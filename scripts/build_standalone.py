"""Maintainer build: one full Windows installer; installed apps never run this."""
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
    parser = argparse.ArgumentParser(description="Build and validate OSII's complete offline Windows installer")
    parser.add_argument("--pilot", action="store_true", help="Allow an explicitly unsigned pilot build")
    args = parser.parse_args()
    if os.name != "nt" or platform.machine().lower() not in {"amd64", "x86_64"}:
        parser.error("Build the Windows x64 installer on Windows x64, or use the Standalone Windows GitHub workflow.")
    if sys.version_info[:2] != (3, 12):
        parser.error("Use the locked Python 3.12 build environment documented in docs/operations/standalone.md.")
    node, npm = shutil.which("node"), shutil.which("npm")
    if not node or not npm:
        parser.error("The build machine needs Node.js 22.18+ and npm. Installed OSII users do not need them.")
    # Execute npm's JS CLI with Node directly; no cmd.exe parsing of paths.
    npm_cli = Path(npm).parent / "node_modules" / "npm" / "bin" / "npm-cli.js"
    if not npm_cli.is_file():
        parser.error("Cannot locate npm's CLI beside npm.cmd. Use the standard Node distribution or GitHub CI.")
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
    executable = desktop / "resources" / "runtime" / "osii-runtime" / "osii-runtime.exe"
    clean = os.environ.copy()
    clean["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
    clean.pop("PYTHONPATH", None)
    clean.pop("PYTHONHOME", None)
    for _ in range(2):
        run([str(executable), "self-test"], environment=clean)
    run([sys.executable, "scripts/check_standalone.py", "--runtime", str(executable)])
    run([node, str(npm_cli), "run", "package:pilot" if args.pilot else "package:windows"], directory=desktop)
    powershell = shutil.which("pwsh") or str(Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe")
    run([powershell, "-NoProfile", "-File", "scripts/check_standalone_installer.ps1", *([] if args.pilot else ["-RequireSignature"])])
    release = ROOT / "release" / "standalone"
    installer = release / "OSII-Standalone-Setup.exe"
    (release / "SHA256SUMS.txt").write_text(hashlib.sha256(installer.read_bytes()).hexdigest() + "  " + installer.name + "\n", encoding="utf-8")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    (release / "validation.json").write_text(json.dumps({"signed": not args.pilot, "cleanWindowsAcceptance": "pending", "commit": commit}, indent=2) + "\n")
    label = "Validated pilot installer: " if args.pilot else "Signed installer: "
    print(label + str(installer))
    print("Clean standard-user Windows acceptance remains required before broad release.")


if __name__ == "__main__":
    main()
