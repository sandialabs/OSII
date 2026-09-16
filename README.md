# OSII

> **Keep the evidence. Grow the intelligence.**

OSII (the On-Store Intelligence Index) turns a folder of documents and datasets
into a library you can browse, search, enrich, and ask questions about. It runs
locally, works without an AI model, and can use approved AI services when they
are available.

Your original files stay where they are: **OSII does not alter them.** It keeps
extracted content, provenance, and rebuildable search data in a neighboring
`.osii` sidecar. You can inspect, move, or rebuild that sidecar without changing
the source material.

## What happens when you use OSII Launcher

Open the launcher and choose a folder of documents. It checks that OSII can
read that folder, helps you connect to the image registry, and lets you select
optional tools. When you press **Start OSII**, it starts a local stack; you can
then open the dashboard from the launcher. You can return to the same library
later without rebuilding the app or repeating the setup.

The launcher handles the workstation; OSII handles the knowledge. Your files
remain untouched and are mounted read-only. OSII extracts text and tables,
records where each result came from, and writes derived artifacts to a separate
`.osii` sidecar. Search indexes can be rebuilt from those artifacts. The
dashboard lets you inspect the results, search, and ask grounded questions.
An AI model is optional, not a prerequisite for understanding your files.

```text
Choose a folder in Launcher
         |
         +--> original files (read-only)
         |
         +--> OSII's .osii sidecar (derived content + provenance)
                         |
                         +--> dashboard, Python, REST, MCP, and custom tools
```

This design reflects four ideas:

- **Grounding before generation.** A model may help interpret material, but
  it is not the source of truth.
- **Canonical files before indexes.** Search indexes and caches make OSII
  fast; they can be rebuilt from inspectable artifacts.
- **Replaceable computation.** You can add or swap extractors, synthesizers,
  embedders, and enrichers without changing your originals.
- **One shared vocabulary.** People, scripts, the dashboard, REST clients,
  and agents use the same objects, scopes, artifacts, and provenance.

## Start here: choose your path

| Path | Best for |
| --- | --- |
| [Desktop app: build the launcher](#desktop-app-build-the-launcher) | The primary graphical path for choosing a library, optional tools, and a pinned container version. |
| [Bare-metal demo](#bare-metal-demo) | Learning OSII or changing Python and dashboard code without building containers. |
| [Direct containers](#direct-containers) | Building and testing the packaged stack yourself. |

### Desktop app: build the launcher

Build the launcher once, then open the resulting app whenever you want to use
OSII. It needs Podman, a Compose provider, and accessible OSII images at a
pinned tag. **Building the launcher does not build the images.** From
`osii-launcher/`, after installing its [development
prerequisites](osii-launcher/README.md#development):

```bash
npm ci
npm run tauri -- build
```

The [launcher guide](osii-launcher/README.md) explains image defaults and where
to find the built app. Configure model connections later in dashboard
**Setup**; model keys do not belong in the launcher.

### Bare-metal demo

For the shortest source-based introduction, install [uv](https://docs.astral.sh/uv/)
and Node.js/npm, then run the demo from the repository root. OSII requests its
tested Python 3.12 runtime and manages the application environment for you.
No container runtime or model download is needed for this path.

```bash
# macOS/Linux (requires make)
make demo
```

```powershell
# Windows PowerShell
.\scripts\osii.ps1 demo
```

Keep that terminal open and visit the [dashboard](http://localhost:5173).
In **Intake**, process the included example files; then explore **Files**,
**Search**, and **Collections**. Stop with Ctrl+C. To run against your own
files later, use `make dev` or `.\scripts\osii.ps1 dev` and follow the
[host-Python runbook](docs/operations/runbook-development.md#host-python-development).

### Direct containers

Use `make build` and `make run` from the repository root on macOS/Linux, or
the [equivalent PowerShell commands](docs/operations/runbook-development.md#direct-compose-development)
on Windows. The [Compose runbook](docs/operations/runbook-development.md#direct-compose-development)
covers the container `.env`, Podman setup, and architecture checks. The
[deployment chooser](docs/operations/runbooks.md) covers other operating tasks.

## Where to go next

| If you want to… | Read… |
| --- | --- |
| Learn the architecture through small examples | [Python demonstration series](osii-demo-notebooks/README.md) |
| Process one file and inspect its artifacts | [Single-file walkthrough](docs/tutorials/single-file.md) |
| Understand Core, processors, and clients | [Architecture](docs/concepts/architecture.md) |
| Add your own extractor, synthesizer, embedder, or enricher | [Extend OSII](docs/extending/index.md) |
| Use shared drives or configure models | [Shared drives](docs/operations/shared-drives.md) · [Model connections](docs/reference/model-providers.md) |
| Find an operating procedure | [Deployment runbooks](docs/operations/runbooks.md) |
| Find a REST route or schema | [REST API overview](docs/reference/api/index.md) · [OpenAPI schema](osii-core/docs/api/openapi.yaml) |

## How this repository is organized

The boundaries are intentional; you do not need to learn them all to use OSII.

- **`osii-core/`** owns the `.osii` sidecar, scopes, retrieval, API, worker,
  and grounded chat. Its `osii.processor_sdk` is the public contract for
  custom processors.
- **`osii-core/services/`** contains the guaranteed baseline processors.
- **`osii-dashboard/`** and **`osii-mcp/`** are human and agent clients of Core.
- **`osii-launcher/`** owns workstation-level Podman, image, folder, profile,
  and application-lifecycle workflows.
- **`osii-toolbox/`** contains optional processors whose dependencies do not
  belong in Core.
- **`osii-demo-notebooks/`**, **`docs/`**, and **`scripts/`** support learning,
  reference, and cross-platform operation.

OSII is a research project and a working implementation of grounded,
extensible knowledge infrastructure. It makes interpretations inspectable—not
authoritative merely because a model produced them. When in doubt, return to
the source material and its provenance.
