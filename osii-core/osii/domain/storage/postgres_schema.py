"""Explicit, account-free PostgreSQL schema for a standalone local library.

The shared read/commit/authoring/job adapters use the same table contracts as
the hosted product. Local initialization never installs hosted authentication.
"""

from __future__ import annotations

VERSION = 1

DDL = (
    "CREATE TABLE osii_local_schema(version integer PRIMARY KEY)",
    "CREATE TABLE datasets(id text PRIMARY KEY, revision integer NOT NULL DEFAULT 0)",
    """CREATE TABLE documents(file_id text PRIMARY KEY, source_relpath text NOT NULL,
        active boolean NOT NULL DEFAULT true, sha256 text NOT NULL, filename text NOT NULL,
        media_type text NOT NULL, size_bytes bigint NOT NULL, text text NOT NULL,
        metadata jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE extractions(id text PRIMARY KEY, file_id text NOT NULL REFERENCES documents ON DELETE CASCADE,
        sha256 text NOT NULL, response jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE chunks(chunk_id text PRIMARY KEY, file_id text NOT NULL REFERENCES documents ON DELETE CASCADE,
        text text NOT NULL, char_start integer NOT NULL, char_end integer NOT NULL,
        source_origin jsonb NOT NULL, embedding jsonb, embedding_model text)""",
    "CREATE INDEX chunks_document ON chunks(file_id)",
    """CREATE TABLE artifacts(id text PRIMARY KEY, file_id text NOT NULL REFERENCES documents ON DELETE CASCADE,
        kind text NOT NULL, payload jsonb NOT NULL)""",
    """CREATE TABLE collections(id text PRIMARY KEY, name text NOT NULL, description text NOT NULL,
        members jsonb NOT NULL, owner_id text, visibility text NOT NULL DEFAULT 'shared')""",
    "CREATE TABLE settings(id text PRIMARY KEY, value jsonb NOT NULL)",
    """CREATE TABLE import_files(import_id text NOT NULL,path text NOT NULL, sha256 text NOT NULL,
        content bytea NOT NULL,PRIMARY KEY(import_id,path))""",
    """CREATE TABLE jobs(id text PRIMARY KEY, status text NOT NULL, kind text NOT NULL,
        payload jsonb NOT NULL, logs jsonb NOT NULL, attempts integer NOT NULL,
        worker_id text, lease_until timestamptz, created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    "CREATE INDEX jobs_claim ON jobs(status,created_at,id)",
    """CREATE TABLE scope_products(id text PRIMARY KEY, scope_type text NOT NULL,
        scope_id text NOT NULL, filename text NOT NULL, family text NOT NULL,
        method text NOT NULL, current_revision text, title text NOT NULL, artifact_type text NOT NULL,
        CONSTRAINT scope_product_address UNIQUE(scope_type,scope_id,filename))""",
    """CREATE TABLE scope_revisions(id text PRIMARY KEY, product_id text NOT NULL REFERENCES scope_products ON DELETE CASCADE,
        parent text, origin text NOT NULL, created_at text NOT NULL, actor_id text,
        data jsonb NOT NULL, provenance jsonb NOT NULL)""",
)


def initialize(engine) -> None:
    """Create only in an empty schema, in one transaction; never adopt a server DB."""
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(914035)"))
        existing = (
            conn.execute(
                text("""SELECT tablename FROM pg_tables
            WHERE schemaname=current_schema()""")
            )
            .scalars()
            .all()
        )
        if existing:
            raise ValueError(
                "Initialization requires an empty PostgreSQL schema; nothing was changed"
            )
        for statement in DDL:
            conn.execute(text(statement))
        conn.execute(
            text("INSERT INTO osii_local_schema VALUES (:version)"),
            {"version": VERSION},
        )
        conn.execute(text("INSERT INTO datasets(id,revision) VALUES ('shared',0)"))


def validate(engine) -> None:
    """Read-only startup check. Schema creation and import are separate commands."""
    from sqlalchemy import text

    with engine.connect() as conn:
        marker = conn.execute(text("SELECT to_regclass('osii_local_schema')")).scalar()
        if not marker:
            raise ValueError(
                "Local PostgreSQL schema is not initialized; run python -m osii.storage_cli init"
            )
        version = (
            conn.execute(text("SELECT version FROM osii_local_schema")).scalars().all()
        )
        if version != [VERSION]:
            raise ValueError(
                "Unsupported local PostgreSQL schema version; no automatic migration was attempted"
            )
