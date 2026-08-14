#!/usr/bin/env python3
"""Launch one independently addressable service from the shared image."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn


SERVICES = {
    "extractor": ("local-extractor", 8092),
    "synthesizer": ("local-synthesizer", 8093),
    "embedder": ("local-embedder", 8085),
    "enricher": ("local-enricher", 8094),
    "model-bridge": ("model-provider-bridge", 8095),
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one OSII baseline processor or model-provider bridge."
    )
    parser.add_argument("service", choices=SERVICES)
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    directory, default_port = SERVICES[args.service]
    service_root = Path(os.getenv("OSII_SERVICE_ROOT", "/workspace/services"))
    app_dir = service_root / directory
    if not app_dir.is_dir():
        raise RuntimeError(f"Service source is missing from the image: {app_dir}")

    port = args.port or int(os.getenv("PORT", str(default_port)))
    uvicorn.run("app.main:app", app_dir=str(app_dir), host=args.host, port=port)


if __name__ == "__main__":
    main()
