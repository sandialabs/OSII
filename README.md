# OSII

> **Keep the evidence. Grow the intelligence.**

OSII (the On-Store Intelligence Index) turns a folder of files into a local,
inspectable intelligence layer. It lets people browse, search, and build on
their own material without handing the original corpus to a single model,
database, or application.

The central promise is simple: OSII leaves source files alone and records its
work in a portable sidecar beside them. Every extracted passage, table,
summary, and answer can retain a path back to the material it came from.

[Start the documentation](docs/index.md) ·
[Learn through Python examples](osii-demo-notebooks/README.md) ·
[Understand the architecture](docs/concepts/architecture.md)

## The idea at a glance

```text
Your files                         OSII's portable sidecar
----------                         -----------------------
reports, PDFs, CSVs, notes  --->   extracted text and source locations
                                   typed tables, entities, and wikis
                                   provenance and processing history
                                   rebuildable search indexes
                                         |
                                         +--> browse, search, chat, Python,
                                              REST, MCP, and custom processors
```

This is why OSII is deliberately modular:

- **Grounding before generation.** A model may help interpret material, but it
  is not the source of truth.
- **Canonical files before indexes.** Search indexes and caches make OSII
  fast; they can be rebuilt. The ordinary `.osii` sidecar remains inspectable.
- **Replaceable computation.** You can swap or add extractors, synthesizers,
  embedders, and enrichers without forking the core or changing your originals.
- **One shared vocabulary.** People, scripts, the dashboard, REST clients, and
  agents use the same objects, scopes, artifacts, and provenance.

## Quick start: explore OSII with the built-in demo

This is the shortest route for a technically curious person who wants to see
OSII working before configuring models, OCR, containers, or custom services.
It uses the local, model-free baseline and public demonstration data.

Before starting, install [uv](https://docs.astral.sh/uv/) and Node.js/npm. On
macOS or Linux, you also need `make`. OSII asks uv for its tested Python 3.12
runtime, so you do not need to create or activate a Python environment. No
container runtime or model download is required for this path.

### macOS or Linux

From the repository root:

```bash
make demo
```

### Windows PowerShell

From the repository root:

```powershell
.\scripts\osii.ps1 demo
```

That one command installs a small public example corpus—one PDF and two
datasets—then starts the complete model-free OSII baseline. It creates and
manages the application environment for you. The first run installs Python and
JavaScript packages and can take a few minutes; later runs reuse them. Keep that
terminal open, then visit:

- **Dashboard:** <http://localhost:5173>
- **Backend health:** <http://localhost:8511/health>

In the dashboard, open **Intake**, choose the example files, and process them.
Then explore **Files**, **Search**, and **Collections**. You should be able to
inspect the extracted content and see what OSII created without needing a
model connection.

The baseline includes document extraction, source-excerpt previews, BM25
search, local enrichment, the worker, API, MCP server, and dashboard. Open
**Setup** afterward to connect Ollama or another AI endpoint, or to start
optional Apache Tika and Tesseract OCR. Ollama and the native Tesseract program
are separate installations; the old standalone MiniLM image is not part of
normal startup.

To stop the local stack, return to the terminal and press <kbd>Ctrl</kbd> +
<kbd>C</kbd>.

### Use your own files instead

Put files in `osii-data/source/`, then run `make dev` on macOS/Linux or
`.\scripts\osii.ps1 dev` on Windows. OSII reads that folder but does not modify
or delete its contents. Its derived data is stored beside it in
`osii-data/.osii/`, which is ignored by Git.

To use a source folder elsewhere on your computer, copy `.env.example` to
`.env` and set `OSII_SOURCE_DIR`. The `.env` file is optional for the default
layout. See [local-first operation](docs/operations/local-first.md) for the
cross-platform details and optional capabilities.

## Choose your next path

| If you want to… | Start here |
| --- | --- |
| Learn the architecture by running small, inspectable examples | [Python demonstration series](osii-demo-notebooks/README.md) |
| Process one file and inspect every resulting sidecar artifact | [Single-file walkthrough](docs/tutorials/single-file.md) |
| Understand why OSII separates core, processors, dashboard, and agents | [Architecture](docs/concepts/architecture.md) |
| Add a custom extractor, synthesizer, embedder, or enricher | [Extend OSII](docs/extending/index.md) |
| Build an external processor against the stable public contract | [Processor API v1](docs/reference/processor-api/index.md) |
| Work with tables and datasets | [Tabular dataset walkthrough](docs/tutorials/tabular-datasets.md) |
| Run packaged deployment images instead of editable source | [Publish and run images](docs/operations/publishing-images.md) |
| Deploy or publish optional OCR, dataset, and embedding tools | [Toolbox: deployment and Quay commands](osii-toolbox/README.md) |
| Find a REST route or schema | [REST API overview](docs/reference/api/index.md) and [OpenAPI schema](osii-core/docs/api/openapi.yaml) |

## How this repository is organized

You do not need to learn the entire monorepo to use OSII. The broad boundaries
are intentional and reflected directly in the root names:

- **`osii-core/`** owns canonical `.osii` persistence, scopes, retrieval, the
  REST API, the worker, and bounded grounded chat.
- **`osii-core/processor-sdk/`** is a small, separately installable contract
  package for custom processors. It lives with Core because Core owns that
  boundary; an external processor does not need to install all of Core.
- **`osii-core/services/`** contains the guaranteed local processor hosts.
  They run automatically during local development and remain independently
  addressable and containerizable.
- **`osii-dashboard/`** and **`osii-mcp/`** are human and agent clients of Core.
- **`osii-toolbox/`** contains optional OCR, dataset, and model-backed tools
  whose heavier dependencies do not belong in Core.
- **`osii-demo-notebooks/`**, **`docs/`**, and **`scripts/`** provide learning,
  reference, and cross-platform operating support.

For operational commands, see the [CLI cheat sheet](docs/reference/cli.md).
For offline behavior, model connections, OCR, and privacy boundaries, see
[local-first operation](docs/operations/local-first.md) and [sensitive data,
transfer, and deletion](docs/operations/sensitive-data.md).

## What OSII is—and is not

OSII is a research project and a working implementation of grounded,
extensible knowledge infrastructure. It is designed to make the structure and
limits of an interpretation visible—not to claim that a model has solved
understanding.

The repository is actively evolving. The stable compatibility boundary for
external extensions is [Processor API v1](docs/reference/processor-api/index.md).
When in doubt, favor the source material, inspect the sidecar, and follow the
provenance.
