# OSII server

`osii-server` runs one authenticated shared library backed by PostgreSQL.
`main` remains the standalone filesystem application. Use separate worktrees and
runtime configuration; transfer portable fixes deliberately.
Keep portable fixes in separate commits and cherry-pick them between branches.
Test both persistence implementations; do not merge the server branch wholesale
into `main`.

Core owns permissions, persistence, provenance, and RAG. The React dashboard is
an HTTP client. Processors use bounded SDK requests and have no database access.
PostgreSQL stores canonical extracted content, chunks, embeddings, artifacts,
collections, settings, accounts, sessions, audit events, and jobs. Originals stay
on a read-only source volume. There is no `.osii` or SQLite fallback.

## Run it

Install uv, Node.js 22.18+, and PostgreSQL 15+. Create an application database,
copy `.env.example` to `.env`, and configure its URL, source directory, and
private provider-key file. Then run:

```bash
uv sync --package osii --extra server --extra dev
uv run --env-file .env --package osii --extra server python -m osii.server.cli migrate
uv run --env-file .env --package osii --extra server python -m osii.server.cli bootstrap-admin --username admin
make dev
```

Open [the server dashboard](http://localhost:5174). API and extractor ports are
8512 and 8192, separate from the standalone defaults. Ctrl+C stops application
services; PostgreSQL stays running. Windows uses `scripts/osii.ps1 dev`
after the same explicit database preparation.

After that one-time preparation, `make dev` is the only startup command,
including after a reboot. To let it start your existing local PostgreSQL cluster,
set `OSII_DEV_POSTGRES_DIR=./osii-data/postgres` in `.env`. It reuses a running
cluster, or starts it on the loopback host/port from `DATABASE_URL` and waits for
connections before starting OSII. Logs go to `osii-data/postgres.log`.
PostgreSQL tools are discovered on PATH or in the matching Homebrew installation;
`OSII_DEV_POSTGRES_BIN` can select their directory explicitly. The tool version
must match the cluster's `PG_VERSION`.

On the current development Mac, PostgreSQL is installed at
`/opt/homebrew/opt/postgresql@18`, with the private OSII cluster in
`osii-data/postgres` on port **55432**. These are the database program and its
persistent data respectively; source documents remain in the source directory.
Starting OSII does not recreate databases, run migrations, or reset accounts.
For an externally managed database, omit `OSII_DEV_POSTGRES_DIR`; OSII uses
`DATABASE_URL` without managing PostgreSQL. OpenShift continues to manage its
database through the deployment resources, independently of this dev launcher.

Administrators manage accounts and model selections. Curators ingest the fixed
dataset and manage shared collections. Readers browse, inspect sources, search,
and chat; they see no setup wizard or administration controls. Temporary account
passwords must change at first login. Password/role changes and disabling an
account revoke its sessions. Bootstrap works only with an empty account database.

Discover model names in **Administration**, choose exact API IDs, save, and
explicitly test invocation. Credentials and endpoint URLs belong to deployment
configuration. Changing the embedding model requires reprocessing. Originals are
never modified. Configure `OSII_OCR_URL` for image-only source documents; an empty
extraction is an error rather than a searchable success.
Use **Reprocess all documents** after changing extraction/OCR behavior; ordinary
processing skips unchanged documents with the same embedding model. Reprocessing
repeats any configured model calls.

## Headless backend and evaluation

Install `osii[server]`, provide configuration, and run
`uvicorn osii.server.api:create_app --factory`. Run ingestion separately with
`python -m osii.server.worker`. Node, the dashboard, MCP, and optional processors
are not required to serve an already-ingested corpus.

API clients call `/api/auth/login`, retain the session cookie, and send the
returned `csrf_token` in `X-CSRF-Token` for writes. `/api/capabilities` describes
supported workflows. OpenAPI documentation requires an administrator session.
`/health` checks the process and `/ready` checks database/schema readiness.

Search combines corrected BM25, Unicode/numeric-aware normalization, bounded
character-similarity expansion, and optional compatible semantic vectors. Source
text and offsets remain unchanged. Private uploads, saved private conversations,
Microsoft SSO, legacy package/editing workflows, and filesystem MCP are deferred.

To evaluate real OCR, prepare an ignored JSONL file containing `query` and
`expected_sources` (relative source paths) per line. Use 30–50 labelled cases:

```bash
uv run --env-file .env --package osii --extra server python -m osii.server.evaluate osii-data/queries.jsonl
```

The evaluator reports source Recall@k and MRR. Semantic/hybrid modes require
`--allow-paid-embeddings`. Synthetic regression tests do not establish quality
on your real corpus.

## Develop and verify

Set `TEST_DATABASE_URL` to an isolated PostgreSQL database ending in `_test`,
then run `make test`. Tests recreate that database's public schema; never use
an application database. They exercise accounts, authorization, CSRF, leases,
transaction rollback, provenance, OCR retrieval, model IDs, and provider errors.

See [deployment and recovery](docs/operations/runbook-server.md) for OpenShift,
images, secrets, source publication, backup/restore, and rollback. Historical
local-first documentation describes `main`, not the server runtime.
