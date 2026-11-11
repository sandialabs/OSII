"""Run one of the independently deployable tabular Processor API services."""

from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an OSII tabular processor.")
    parser.add_argument("service", choices=("extractor", "enricher"))
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    application = f"tabular_processors.main:{args.service}_app"
    default_port = 8097 if args.service == "extractor" else 8098
    uvicorn.run(application, host=args.host, port=args.port or default_port)


if __name__ == "__main__":
    main()
