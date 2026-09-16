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

## Start here: choose your path

| What you want | Start with | Best for |
| --- | --- | --- |
| **A desktop app** | [Build the Tauri launcher](osii-launcher/README.md#development) | Choosing a library folder, optional tools, and a pinned container release in a graphical app; then starting and stopping OSII repeatably. |
| **A bare-metal development run** | `make demo` on macOS/Linux or `.\scripts\osii.ps1 demo` on Windows | Learning OSII or changing its Python and dashboard code without building containers. |
| **Direct containers** | `make build` then `make run`, or the [PowerShell equivalents](docs/operations/runbook-development.md#direct-compose-development) | Building and testing the packaged stack yourself. |

The launcher is the primary desktop experience. Build it once, then open the
resulting app when you want to use OSII. It needs Podman, a Compose provider,
and accessible OSII images at a pinned tag; **building the launcher does not
build the images**. From `osii-launcher/`, after installing its [development
prerequisites](osii-launcher/README.md#development):

```bash
npm ci
npm run tauri -- build
```

The [launcher guide](osii-launcher/README.md) explains image defaults and where
to find the built app. In the app, choose a document folder, connect to the
image registry, select optional tools, and start OSII. Configure model
connections later in dashboard **Setup**; model keys do not belong in the
launcher.

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

For direct containers, start with the
[Compose runbook](docs/operations/runbook-development.md#direct-compose-development).
It covers the container `.env`, Podman setup, architecture checks, and the
equivalent Windows commands. The [deployment chooser](docs/operations/runbooks.md)
also covers desktop use, releases, updates, and rollback.

## What happens when you use OSII

```text
Your files                         OSII's portable sidecar
----------                         -----------------------
reports, PDFs, CSVs, notes  --->   extracted text and source locations
                                   tables, enrichments, and provenance
                                   rebuildable search indexes
                                         |
                                         +--> dashboard, Python, REST, MCP,
                                              and custom processors
```

Four ideas guide the project:

- **Grounding before generation.** A model may help interpret material, but
  it is not the source of truth.
- **Canonical files before indexes.** Search indexes and caches make OSII
  fast; they can be rebuilt from inspectable artifacts.
- **Replaceable computation.** You can add or swap extractors, synthesizers,
  embedders, and enrichers without changing your originals.
- **One shared vocabulary.** People, scripts, the dashboard, REST clients,
  and agents use the same objects, scopes, artifacts, and provenance.

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
