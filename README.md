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

## A look at OSII

> **Screenshot placeholder — browse a grounded library**
>
> A wide screenshot of the dashboard's Files or document view will live here:
> source material on one side, extracted or derived material on the other, and
> visible provenance linking them.

> **Screenshot placeholder — search with evidence**
>
> A second screenshot will show a scoped search or chat result with its source
> citations. Until then, the quick start below gets you to the same screen.

## Quick start: explore OSII with the built-in demo

This is the shortest route for a technically curious person who wants to see
OSII working before configuring models, OCR, containers, or custom services.
It uses the local, model-free baseline and public demonstration data.

Before starting, install Python 3.11, [uv](https://docs.astral.sh/uv/), and
Node.js/npm. On macOS or Linux, you also need `make`. No container runtime or
model download is required for this path.

### macOS or Linux

From the repository root:

```bash
cp .env.example .env
make demo-data
make dev
```

### Windows PowerShell

From the repository root:

```powershell
Copy-Item .env.example .env
.\scripts\osii.ps1 demo-data
.\scripts\osii.ps1 dev
```

The first command installs a small public example corpus: one PDF and two
datasets. The second starts OSII from source and manages its application
environment for you. Keep that terminal open, then visit:

- **Dashboard:** <http://localhost:5173>
- **Backend health:** <http://localhost:8511/health>

In the dashboard, open **Intake**, choose the example files, and process them.
Then explore **Files**, **Search**, and **Collections**. You should be able to
inspect the extracted content and see what OSII created without needing a
model connection.

To stop the local stack, return to the terminal and press <kbd>Ctrl</kbd> +
<kbd>C</kbd>.

### Use your own files instead

Put files in `osii-data/source/`, then start OSII using the same `dev` command.
OSII reads that folder but does not modify or delete its contents. Its derived
data is stored beside it in `osii-data/.osii/`, which is ignored by Git.

To use a source folder elsewhere on your computer, set `OSII_SOURCE_DIR` in
the repository-root `.env`. See [local-first operation](docs/operations/local-first.md)
for the cross-platform details and optional capabilities.

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
| Find a REST route or schema | [REST API overview](docs/reference/api/index.md) and [OpenAPI schema](ai-ready-ingest/docs/api/openapi.yaml) |

## How this repository is organized

You do not need to learn the entire monorepo to use OSII. The broad boundaries
are intentional:

- **OSII Core** owns canonical `.osii` persistence, scopes, retrieval, and
  grounded chat orchestration.
- **Dashboard, REST API, and MCP** are different ways to use that same core
  data rather than competing stores of knowledge.
- **`osii_processor_sdk`** is the friendly, typed public surface for custom
  processors.
- **Processor services** perform bounded compute and return typed results;
  Core validates provenance and saves canonical outputs.
- **Documentation and demonstrations** explain the concepts before the
  machinery, so new contributors can adapt OSII without copying hidden setup.

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
