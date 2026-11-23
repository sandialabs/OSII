"""Explicit schema migration and protected initial administrator bootstrap."""
import argparse
import getpass
from pathlib import Path

from alembic import command
from alembic.config import Config

from osii.persistence.postgres import PostgresStore
from osii.server.auth import password_hash
from osii.server.config import Settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["migrate", "bootstrap-admin"])
    parser.add_argument("--username", default="admin")
    args = parser.parse_args()
    settings = Settings.environment()
    if args.action == "migrate":
        config = Config()
        config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "persistence" / "migrations"))
        config.attributes["database_url"] = settings.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        command.upgrade(config, "head")
        print("Database schema is current.")
    else:
        import re
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,99}", args.username):
            parser.error("Use a lowercase username with letters, numbers, dots, underscores, or hyphens")
        password = getpass.getpass("Administrator password (15–128 characters): ")
        if password != getpass.getpass("Repeat password: "):
            parser.error("Passwords do not match")
        store = PostgresStore(settings.database_url)
        store.ready()
        store.create_account(args.username, password_hash(password), "admin", bootstrap=True)
        print("Administrator created. Sign in through the dashboard.")


if __name__ == "__main__":
    main()
