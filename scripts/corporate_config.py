"""Validate private corporate defaults and prepare non-secret local settings."""

from __future__ import annotations

import argparse
import json
import os
import re
import tomllib
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "corporate/osii.toml"
REQUIRED = {
    "OSII_QUAY_REGISTRY", "OSII_IMAGE_PREFIX", "OSII_BASE_IMAGE",
    "OSII_TESSERACT_SOURCE_URL", "OSII_LEPTONICA_SOURCE_URL",
    "OSII_TESSDATA_BASE_URL", "OSII_MODEL_BASE_URL", "OSII_CATALOG_URL",
}
OPTIONAL = {"OSII_EMBEDDING_MODEL", "OSII_CHAT_MODEL", "OSII_CA_BUNDLE"}
ALLOWED = REQUIRED | OPTIONAL


def load_defaults(path: Path = DEFAULT_PATH) -> dict[str, str]:
    if not path.is_file():
        raise ValueError(f"Create {path} in the corporate repository with non-secret [defaults].")
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    if set(document) != {"defaults"} or not isinstance(document["defaults"], dict):
        raise ValueError("Corporate settings must contain only a [defaults] table.")
    defaults = document["defaults"]
    unknown = set(defaults) - ALLOWED
    missing = REQUIRED - set(defaults)
    if unknown or missing:
        raise ValueError(f"Corporate settings: unknown {sorted(unknown)}; missing {sorted(missing)}.")
    if any(not isinstance(value, str) for value in defaults.values()):
        raise ValueError("Corporate defaults must be strings; never put credentials here.")
    if any(not defaults[key].strip() for key in REQUIRED):
        raise ValueError("Required corporate defaults cannot be blank.")
    if any("example" in value.lower() or "your-" in value.lower() for value in defaults.values()):
        raise ValueError("Replace all illustrative domains and placeholders in corporate settings.")
    registry = defaults["OSII_QUAY_REGISTRY"].rstrip("/")
    prefix = defaults["OSII_IMAGE_PREFIX"].rstrip("/")
    if "://" in registry or "/" in registry or prefix != f"{registry}/ai-ready-everything/osii":
        raise ValueError("OSII_IMAGE_PREFIX must be the approved corporate Quay /ai-ready-everything/osii prefix.")
    if registry in {"quay.io", "localhost"}:
        raise ValueError("Use corporate Quay, not a public or local registry.")
    if not re.search(r"@sha256:[0-9a-f]{64}$", defaults["OSII_BASE_IMAGE"]):
        raise ValueError("OSII_BASE_IMAGE must be an approved immutable digest reference.")
    for name in REQUIRED & {"OSII_TESSERACT_SOURCE_URL", "OSII_LEPTONICA_SOURCE_URL",
                            "OSII_TESSDATA_BASE_URL", "OSII_MODEL_BASE_URL", "OSII_CATALOG_URL"}:
        if not defaults[name].startswith("https://"):
            raise ValueError(f"{name} must use HTTPS.")
    catalog = urllib.parse.urlparse(defaults["OSII_CATALOG_URL"])
    if catalog.username or catalog.password or catalog.query or catalog.fragment:
        raise ValueError("OSII_CATALOG_URL must not contain credentials or query parameters.")
    return {key: value.strip() for key, value in defaults.items()}


def apply_defaults(path: Path = DEFAULT_PATH) -> None:
    """Environment values take precedence; private defaults contain no secrets."""
    if path.is_file():
        for name, value in load_defaults(path).items():
            os.environ.setdefault(name, value)


def render_files(defaults: dict[str, str], version: str) -> dict[Path, str]:
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", version):
        raise ValueError("Use an immutable X.Y.Z release version, not latest.")
    compose = {
        "OSII_IMAGE_PREFIX": defaults["OSII_IMAGE_PREFIX"],
        "OSII_IMAGE_TAG": version,
        "OSII_BASE_IMAGE": defaults["OSII_BASE_IMAGE"],
        "OSII_TESSERACT_SOURCE_URL": defaults["OSII_TESSERACT_SOURCE_URL"],
        "OSII_LEPTONICA_SOURCE_URL": defaults["OSII_LEPTONICA_SOURCE_URL"],
        "OSII_TESSDATA_BASE_URL": defaults["OSII_TESSDATA_BASE_URL"],
        "OSII_MODEL_BASE_URL": defaults["OSII_MODEL_BASE_URL"],
        "OPENAI_BASE_URL": defaults["OSII_MODEL_BASE_URL"],
    }
    launcher = {
        "VITE_OSII_REGISTRY": defaults["OSII_QUAY_REGISTRY"],
        "VITE_OSII_CATALOG_URL": defaults["OSII_CATALOG_URL"],
        "VITE_OSII_IMAGE_PREFIX": defaults["OSII_IMAGE_PREFIX"],
        "VITE_OSII_IMAGE_TAG": version,
        "VITE_OSII_OPENAI_BASE_URL": defaults["OSII_MODEL_BASE_URL"],
        "VITE_OSII_OPENAI_EMBEDDING_MODEL": defaults.get("OSII_EMBEDDING_MODEL", ""),
        "VITE_OSII_OPENAI_CHAT_MODEL": defaults.get("OSII_CHAT_MODEL", ""),
    }
    return {
        ROOT / ".env": "".join(f"{key}={json.dumps(value)}\n" for key, value in compose.items()),
        ROOT / "osii-launcher/.env.local": "".join(
            f"{key}={json.dumps(value)}\n" for key, value in launcher.items()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "write"))
    parser.add_argument("--config", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    defaults = load_defaults(args.config)
    outputs = render_files(defaults, args.version)
    if args.command == "write":
        occupied = [str(path) for path, content in outputs.items()
                    if path.exists() and path.read_text(encoding="utf-8") != content]
        if occupied:
            raise ValueError("Refusing to overwrite existing local settings: " + ", ".join(occupied))
        for path, content in outputs.items():
            if not path.exists():
                path.write_text(content, encoding="utf-8")
    print("Corporate defaults valid; " +
          ("created " + ", ".join(str(path.relative_to(ROOT)) for path in outputs)
           if args.command == "write" else "no files changed"))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from error
