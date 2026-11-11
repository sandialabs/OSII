"""Explicit local database administration: never part of normal app startup."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from osii.domain.storage.backend import BackendSettings, postgres_engine


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "init", help="Create an account-free local schema in an EMPTY database schema"
    )
    commands.add_parser(
        "status", help="Check the explicitly selected local PostgreSQL schema"
    )
    migrate = commands.add_parser(
        "import-sidecars",
        help="Preview a one-way import; --apply explicitly writes to an EMPTY destination",
    )
    migrate.add_argument(
        "source",
        type=Path,
        help="Existing .osii directory; original documents are never copied or modified",
    )
    migrate.add_argument(
        "--apply",
        action="store_true",
        help="Apply the import transaction; without this flag the command only previews",
    )
    args = parser.parse_args(argv)
    engine = None
    try:
        # A preview does not even require a PostgreSQL driver or connection.
        if args.command == "import-sidecars":
            from osii.domain.storage.sidecar_import import plan_import, apply_import

            plan = plan_import(args.source)
            if not args.apply:
                print(json.dumps({**plan.summary(), "imported": False}, indent=2))
                return 0
        settings = BackendSettings.from_environment()
        if settings.kind != "postgres":
            raise ValueError(
                "Explicitly set OSII_STORAGE_BACKEND=postgres and DATABASE_URL for this command"
            )
        engine = postgres_engine(settings)
        if args.command == "init":
            from osii.domain.storage.postgres_schema import initialize

            initialize(engine)
            result = {"initialized": True, "user_authentication": False}
        elif args.command == "status":
            from osii.domain.storage.postgres_schema import validate

            validate(engine)
            result = {"backend": "postgres", "schema_ready": True}
        else:
            result = apply_import(engine, plan)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, FileNotFoundError) as exc:
        # Domain errors contain no DSN or credentials. Database/driver errors
        # intentionally do not get printed verbatim (they may contain URLs).
        parser.exit(2, f"{exc}\n")
    except Exception:
        parser.exit(
            2,
            "PostgreSQL operation failed; verify connectivity, permissions and schema readiness. No automatic fallback or source migration was attempted.\n",
        )
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
