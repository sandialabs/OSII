"""Fixed-role entry point for the frozen OSII runtime."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


def resources() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[3] / "osii-desktop" / "resources"


def configure_ocr() -> None:
    root = resources() / "ocr"
    binary = root / ("tesseract.exe" if os.name == "nt" else "tesseract")
    if not binary.is_file():
        raise RuntimeError("The bundled OCR engine is missing. Reinstall OSII; no system Tesseract installation is required.")
    os.environ["OSII_TESSERACT_EXECUTABLE"] = str(binary)
    os.environ["TESSDATA_PREFIX"] = str(root / "tessdata")


def main() -> int:
    parser = argparse.ArgumentParser(description="OSII packaged runtime")
    parser.add_argument("role", choices=["self-test"])
    args = parser.parse_args()
    configure_ocr()
    if args.role == "self-test":
        from .selftest import run
        print(json.dumps(run()), flush=True)
    return 0
