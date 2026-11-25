# OSII

OSII turns documents and datasets into a library you can browse, search, and ask
questions about. It keeps originals intact and links results to their evidence.
Basic text extraction and keyword search work offline.

- **Use OSII on Windows.** Download the installer from [GitHub Releases](https://github.com/sandialabs/OSII/releases).
  Windows packaging lives on [`osii-standalone`](https://github.com/sandialabs/OSII/tree/osii-standalone).
- **Develop OSII.** Use `main` for the shared Python Core, React dashboard, and
  local source workflow described below.
- **Run a shared library.** Use [`osii-server`](https://github.com/sandialabs/OSII/tree/osii-server)
  for the hosted app with accounts and PostgreSQL.

## Run from source

Install uv and Node.js 22.18+. Copy `.env.example` to `.env` and set
`OSII_SOURCE_DIR` to an existing document folder. Run `make dev` on macOS or
Linux, or `.\scripts\osii.ps1 dev` in Windows PowerShell. Open the dashboard at
`http://localhost:5173`.

See the [development guide](docs/operations/runbook-development.md) for setup,
[architecture](docs/concepts/architecture.md) for the design, and the
[frontend extension guide](docs/extending/frontend-tools.md) to add a Toolbox item.

With PostgreSQL selected, use the [read-only database explorer](docs/reference/database-query.md)
to inspect library records.
