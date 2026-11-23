# OSII

> Keep the evidence. Grow the intelligence.

OSII turns documents and datasets into a library you can browse, search, enrich,
and ask questions about. It keeps originals unchanged and links results to their
source evidence. Extraction, OCR, and keyword search work without an AI model.

## Install OSII Standalone on Windows

Download `OSII-Standalone-Setup.exe` from [GitHub Releases](https://github.com/sandialabs/OSII/releases),
run it on Windows 11 x64, and open **OSII Standalone** from the Start menu. Choose
**Create library** or **Open existing library**, then select your document folder.
The installer includes the dashboard, Python, and OCR. Model setup is optional.

The available Windows pilot is unsigned. See the [desktop guide](docs/operations/standalone.md)
for installation, existing libraries, and updates.

## Develop or deploy from source

| Goal | Branch | Entry point |
| --- | --- | --- |
| Install or try the Windows app | No checkout needed | [GitHub Releases](https://github.com/sandialabs/OSII/releases) |
| Develop OSII locally (OSII Dev) | `main` | `make dev` or `scripts/osii.ps1 dev` |
| Build the Windows installer | `main` | [Standalone Windows build](docs/operations/standalone.md#build-an-installer) |
| Develop or deploy the hosted server | `main` | [Server runbook](docs/operations/runbook-server.md) |

The desktop and hosted projects share the Core and React dashboard on `main`.
The earlier `osii-standalone` and `osii-server` branches are available for
reference and maintenance of earlier deployments.

For **OSII Dev**, switch to `main`, install uv and Node.js 22.18+, copy
`.env.example` to `.env`, and set `OSII_SOURCE_DIR` to an existing folder.
Run `make dev` on macOS/Linux or `.\scripts\osii.ps1 dev` in PowerShell.
Open the dashboard at `http://localhost:5173`. See the [development guide](docs/operations/runbook-development.md)
for startup options and optional processors.

For **OSII Server**, use the hosted profile on `main`. It provides sign-in and
shared library administration with PostgreSQL. The
[server runbook](docs/operations/runbook-server.md) covers the database,
development launcher, and hosted builds.

See the [architecture](docs/concepts/architecture.md) and [extension guide](docs/extending/index.md)
for shared Core, dashboard, and Processor API boundaries. Optional Python
notebooks and the MCP client live on `osii-demo-notebooks` and `osii-mcp`.
