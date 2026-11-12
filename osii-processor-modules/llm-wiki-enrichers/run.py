"""Run one of the independently registered wiki enrichment services."""

from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an OSII wiki enricher.")
    parser.add_argument("service", choices=("readable", "concept-entity"))
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    module = "readable_app" if args.service == "readable" else "concept_entity_app"
    default_port = 8099 if args.service == "readable" else 8100
    uvicorn.run(
        f"wiki_enrichers.main:{module}",
        host=args.host,
        port=args.port or default_port,
    )


if __name__ == "__main__":
    main()
