# OSII

`main` is the standalone, filesystem-backed application. Hosted PostgreSQL,
accounts, and OpenShift development live on the separate `osii-server` branch.
Use separate worktrees and runtime configuration; transfer portable improvements
deliberately rather than merging server persistence into this branch.
Keep portable fixes in separate commits and cherry-pick them between branches;
test each against its own persistence implementation.

> Keep the evidence. Grow the intelligence.

OSII (the On-Store Intelligence Index) turns documents and datasets into a
library you can browse, search, enrich, and ask questions about. Core owns the
data and grounded retrieval; the dashboard is its browser interface. Original
files remain unchanged. Extracted text, provenance, and rebuildable search data
live in the managed `.osii` store.

## Run it

Install **uv**, **Node.js 22.18 or newer**, and **make** on macOS/Linux.
uv manages Python 3.12 and the application environment. For scanned documents,
also install the native **Tesseract** program; ordinary text extraction and
search do not require OCR or a model.

From the repository root:

```bash
make dev
```

On Windows, install uv and Node.js and use PowerShell:

```powershell
.\scripts\osii.ps1 dev
```

The command installs dependencies and starts the API, worker, dashboard, MCP,
and baseline processors on the host. Keep the terminal open. Visit
[the dashboard](http://localhost:5173); check
[Core health](http://localhost:8511/health). Stop with **Ctrl+C**.
No container runtime, Rust, desktop app, or registry login is required.

For example files, use `make demo` (Windows: `.\scripts\osii.ps1 demo`).
For your own files, copy `.env.example` to `.env` once, set
`OSII_SOURCE_DIR` to an existing folder, then run `make dev`.
Connect shared drives through the operating system first. Runtime data and
configuration default to `osii-data/` in this checkout; keep that directory
when updating source.

Configure the team's OpenAI-compatible endpoint through `OPENAI_BASE_URL`,
`OPENAI_CHAT_MODEL`, and optionally `OPENAI_EMBEDDING_MODEL` in `.env`,
or use dashboard **Setup**. Keep credentials outside Git. Existing saved model
configuration is retained across restarts. Basic extraction and keyword search
work without a model.

See the [start and troubleshooting guide](docs/operations/runbook-development.md)
for prerequisites, configuration, updates, and health checks.

## Current scope

Development now targets one shared OSII service on OpenShift, one configured
model endpoint, and a shared database. That is the direction, not a claim that
the current application is already a multi-user hosted service or that its
existing stores have been consolidated. For now the supported, testable way
to run this checkout is the host workflow above. Storage migrations,
authentication, and OpenShift deployment will be explicit future work.

Desktop installers, workstation image catalogs, Compose deployments,
multi-architecture publishing, and component export workflows are archived on
`archive/workstation-deployment-2026-11-03` at commit
`0cc430e45cb0e47ee0fd6fc0681bf40c8167bce0`. They are no longer supported
entry points on `main`. See [deployment status](docs/operations/runbooks.md).

## Repository boundaries

- `osii-core/`: canonical store, retrieval, API, worker, chat, and Processor SDK.
- `osii-core/services/`: baseline processors and the model provider adapter.
- `osii-dashboard/`: browser interface to Core.
- `osii-mcp/`: agent client.
- `osii-toolbox/`: optional processor implementations, kept for product work.
- `osii-demo-notebooks/`: Python demonstrations.
- `docs/`: architecture, APIs, and operating guidance.

## Develop and verify

`make test` runs Core, SDK, baseline processor, and dashboard checks.
`make docs` validates documentation. `make doctor` reports disk usage.

- [Architecture](docs/concepts/architecture.md)
- [Processor API specification](docs/reference/processor-api/index.md)
- [REST API](docs/reference/api/index.md)
- [Python demonstrations](osii-demo-notebooks/README.md)
- [Hosted-service planning](docs/planning/hosted-service.md)
