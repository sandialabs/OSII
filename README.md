# OSII — server

> Keep the evidence. Grow the intelligence.

OSII (the On-Store Intelligence Index) turns documents and datasets into a
library people can browse, search, and ask questions about. The `osii-server`
branch brings that library to a team through one authenticated service, with
shared content in PostgreSQL and deployment guidance for OpenShift.

The source material is the evidence. Originals remain unchanged, extracted
content retains its provenance, and answers link back to supporting passages.
The service manages the shared library and permissions; replaceable processors and
model services help interpret the material without becoming the source of truth.

## What you can do

- Ingest a shared source folder, with optional OCR for scanned documents.
- Browse sources, organize shared collections, and search by keywords or meaning.
- Ask grounded questions using a configured model service.
- Give administrators, curators, and readers appropriate access to the library.

## Get started

Install **uv**, **Node.js 22.18+**, and **PostgreSQL 15+**, plus **make** on
macOS/Linux. Create an application database, copy `.env.example` to `.env`, and
configure the database URL, source directory, and private model-provider
credentials. Then run:

```bash
uv sync --package osii --extra server --extra dev
uv run --env-file .env --package osii --extra server python -m osii.server.cli migrate
uv run --env-file .env --package osii --extra server python -m osii.server.cli bootstrap-admin --username admin
make dev
```

Open [the dashboard](http://localhost:5174), sign in, configure models in
**Setup**, and process the shared dataset. After initial preparation,
start with `make dev` (Windows: `.\scripts\osii.ps1 dev`). **Ctrl+C** stops the
application; PostgreSQL stays running. Keep credentials outside Git.

See the [server runbook](docs/operations/runbook-server.md) for configuration,
headless use, evaluation, OpenShift deployment, and recovery. Use `main` for
OSII-local and its portable filesystem library;
`archive/workstation-deployment-2026-11-03` preserves earlier workstation
packaging workflows.
