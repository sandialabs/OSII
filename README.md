# OSII Standalone

> Download OSII Standalone for Windows or Apple Silicon from [GitHub Releases](https://github.com/sandialabs/OSII/releases).
> Build the installers from `osii-standalone` using the [Standalone build guide](docs/operations/standalone.md).
> Use `main` for shared Core and dashboard development.

> Keep the evidence. Grow the intelligence.

OSII (the On-Store Intelligence Index) turns documents and datasets into a
library you can browse, search, enrich, and ask questions about.
OSII Standalone is a desktop application for files on your computer
or an already-connected shared drive. The Windows and Apple Silicon packages include Python, the
dashboard, native document extraction, and full-page OCR.
It runs without user accounts or a login; OSII-server provides hosted user access.

The source material is the evidence. OSII keeps originals unchanged and saves
extracted content and provenance in portable `.osii` sidecars. An optional
PostgreSQL backend remains available for [source deployments](docs/reference/local-storage.md).
The desktop application uses sidecars. Search indexes
are rebuildable, processors are replaceable, and model interpretations remain
traceable to their sources. Basic extraction and keyword search work without
an AI model.

## What you can do

- Choose files from local folders or a connected share and process them with a
  named flow. The desktop includes offline extraction, previews, keyword search,
  and semantic search with EmbeddingGemma 2.
- Extract text, add OCR alongside it, and inspect text or mathematical Markdown
  with source locations.
- Browse files and collections, search by keywords or document meaning, and ask
  grounded questions with an optional model connection.
- Edit summaries, metadata, wikis, and other derived products with revision
  history; run replaceable analysis tools.
- Explore related documents with the experimental Topic Explorer.
- Create focused collections from topic suggestions or a prompt; see
  [how suggestions work](docs/reference/collection-suggestions.md).
- Compare experimental RAG strategies and inspect their evidence in Chat.
- Extend processing and frontend tools through documented interfaces.
- Write editable research reports with passage references, bibliography drafts,
  reviewable revisions, and Markdown or Mathpix exports.

The **Toolbox** contains frontend workflows. Backend **processor modules**
(Extractors, Synthesizers, Embedders, and Enrichers) live in
`osii-processor-modules/` and use the shared Processor API.

## Get started

Run the Windows x64 `OSII-Standalone-Setup.exe` from the project's release
artifacts, open **OSII Standalone** from the Start menu, and choose **Create
library** or **Open existing library**. Select your document folder and start
working. Basic extraction, OCR and keyword search work offline; model
connections are optional. No terminal or separately installed development tools
are required. Builds labeled **pilot** are unsigned validation builds.

See [installation, existing libraries and updates](docs/operations/standalone.md).

### Develop from source

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
library. Source-development processor modules start automatically and are available in **Setup**.
Set individual `OSII_ENABLE_…` switches in `.env` to omit modules.
Keep the terminal open; **Ctrl+C** stops OSII. For sample files, use
`make demo` (Windows: `.\scripts\osii.ps1 demo`). Install Tesseract for OCR when
running from source. Configure optional model connections in **Setup**. The
[Banyan processor module](osii-processor-modules/banyan/README.md) uses its
own local Nemotron endpoint configuration. Keep credentials outside Git.
Choose a processing flow for selected files. The startup guide covers provider
profiles and configurable processing defaults.

See the [startup guide](docs/operations/runbook-development.md) for setup and
troubleshooting, [architecture](docs/concepts/architecture.md) for the design,
and [extension guides](docs/extending/index.md) for processors and frontend tools.
Use the `osii-server` branch for an authenticated library shared by a team;
`archive/workstation-deployment-2026-11-03` preserves earlier workstation
packaging workflows.

Optional [Python demos](docs/tutorials/python-demonstrations.md) and the agent
interface are separate downloads on the `osii-demo-notebooks` and `osii-mcp`
branches. Each branch contains only that tool.
