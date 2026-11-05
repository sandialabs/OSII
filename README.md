# OSII — local

> Keep the evidence. Grow the intelligence.

OSII (the On-Store Intelligence Index) turns documents and datasets into a
library you can browse, search, enrich, and ask questions about. The `main`
branch is OSII-local: a standalone application for working with files on your
computer or a shared drive mounted on it.

The source material is the evidence. OSII keeps originals unchanged and saves
extracted content and provenance in portable `.osii` sidecars. Search indexes
are rebuildable, processors are replaceable, and model interpretations remain
traceable to their sources. Basic extraction and keyword search work without
an AI model.

## What you can do

- Extract text, with optional OCR for scanned documents, and inspect the sources.
- Browse files and collections, search by keywords or document meaning, and ask
  grounded questions with an optional model connection.
- Explore related documents with the experimental Topic Explorer.
- Extend processing and frontend tools through documented interfaces.

## Get started

Install **uv**, **Node.js 22.18+**, and **make** on macOS/Linux. Copy
`.env.example` to `.env`, set `OSII_SOURCE_DIR` to an existing folder, and run:

```bash
make dev
```

On Windows, install uv and Node.js and run:

```powershell
.\scripts\osii.ps1 dev
```

Open [the dashboard](http://localhost:5173), process your files, and explore the
library. Toolbox services start automatically and are available in **Setup**;
choose a tool when you want to use it. Keep the terminal open; **Ctrl+C** stops
OSII. For sample files, use
`make demo` (Windows: `.\scripts\osii.ps1 demo`). Install Tesseract for OCR;
configure optional model connections in **Setup**. Keep credentials outside Git.

See the [startup guide](docs/operations/runbook-development.md) for setup and
troubleshooting, [architecture](docs/concepts/architecture.md) for the design,
and [extension guides](docs/extending/index.md) for processors and frontend tools.
Use the `osii-server` branch for an authenticated library shared by a team;
`archive/workstation-deployment-2026-11-03` preserves earlier workstation
packaging workflows.

For inventory-first work across large shared volumes, the database-backed
workflow runs on a workstation or SSH-accessible node without a database
service. It discovers metadata before selectively extracting and searching
content. See [large-volume operation](docs/operations/large-volumes.md).
