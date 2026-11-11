# Extend OSII

To add a browser workflow rather than a processor, follow
[Extend the Workbench frontend](frontend-tools.md). The topic explorer shows
how a tool connects to Core-owned embeddings through a typed API.

For retrieval, reranking, or iterative question-answering ideas, use the
[Core RAG strategy authoring guide](rag-strategies.md). RAG extensions are separate
from the four processor kinds below.

An OSII processor is a small HTTP service that performs one specialized task.
It receives a self-contained, validated request and returns grounded text or a
standard artifact. It never writes directly to the OSII store.

## Processor module layout

Use one folder per module under `osii-processor-modules/`: implementation,
`pyproject.toml`, configuration template, tests, and README stay together.
`banyan/` is a consolidated example; `tika-adapter/` also demonstrates an owned
runtime. Add a `processor-module.toml` to declare launch and registration metadata;
OSII discovers it and derives enable/port switches automatically. No central Python
list or `.env.example` edit is required. Follow the
[manifest authoring guide](processor-modules.md). **Toolbox** is the frontend collection of tools.
Existing `toolbox.*` processor IDs remain stable for saved-route compatibility.

## Choose a processor kind

| You need to… | Kind | Typical input | Output |
|---|---|---|---|
| Recover the canonical text or source structure | **Extractor** | Source bytes and metadata | Text segments and source-derived artifacts |
| Explain or summarize existing grounded text | **Synthesizer** | An object, folder, collection, or root scope | Grounded Markdown and citations |
| Convert identified text into vectors | **Embedder** | Ordered IDs and text | Vectors in the same order |
| Add domain-specific structured knowledge | **Enricher** | Existing text and scope metadata | Tables, graphs, entities, or wiki Markdown |

Use an extractor when your parser defines what the source fundamentally says.
Use an enricher when it adds a specialist interpretation alongside canonical
text. For example, recovering text from a laboratory PDF is extraction;
turning that recovered text into an experiment-results table or LLM wiki is
enrichment. The exact output boundary is summarized in
[canonical Processor API outputs](../reference/processor-api/canonical-outputs.md).

## The extension path

1. Start with the [four processor APIs](../reference/processor-api/index.md)
   and the working example for your processor kind.
2. Copy the closest implementation from
   `osii-core/processor-sdk/examples/`.
3. Give the processor a stable descriptor name and semantic version.
4. Implement the one method for its processor kind.
5. Test representative, redistributable examples locally.
6. Add its [module manifest](processor-modules.md), then restart `make dev`.
7. Find it in **Setup**; configure any model bindings and processing settings.
8. Use **Health** to test liveness and **Test** to validate the v1 contract.
9. Run it against an ingested file and inspect the result in the dashboard.

For services deployed independently, **Setup → Advanced & diagnostics → Custom
Processor API services** can register an existing endpoint manually. Enter only
the base URL reachable by Core; OSII appends descriptor and operation paths.
Manifest discovery manages local module startup; remote deployments remain explicit.

## What OSII handles for you

- versioned and strict request and response models;
- `/health` and `/v1/descriptor`;
- the kind-specific operation endpoint;
- canonical persistence and provenance;
- dashboard and agent views for standard artifacts.

Read the [processor development rules](processor-development.md) before
building a production processor, then use the
[Processor API reference](../reference/processor-api/index.md) for exact
payloads.

The [hello enricher walkthrough](hello-enricher.md) provides additional context
for integrating a domain service with the dashboard.

Core has commit adapters for all four Processor API kinds. External processors
remain bounded services: they receive explicit data, return a typed response,
and never mount or write the OSII store.


The shared inventory reader lives in `domain/processing/directory_scan.py` and
reads directory entries/stat metadata only. Local `volume/scanner.py` retains
SQLite persistence and processing coordination; hosted Core supplies PostgreSQL
and worker adapters. The shared discovery and scope-tool widgets accept optional
capability metadata rather than embedding hosted accounts or storage access.
`configureApiClient` lets the hosted composition supply transport policy; local
continues to use its account-free loopback API.


Whole-scope processing uses the shared `domain/processing/scope_batches.py`
engine and `BatchStorage` protocol. The request boundary is bounded while the
corpus has no fixed document or total-text cutoff. Follow the
[batch contract](../reference/processor-api/enrichment.md#whole-scope-batches)
when adding a tool: preserve every supplied text window, return relative
citations, and declare whether derived wiki summaries can be combined. The
shared `ScopeBatchResults` component loads result metadata by page and opens
individual results on demand.


### Workbench landing page

Home (`/`) presents six document tools; Files (`/files`) retains the flat library.
Analyze Library opens the overview, whose **All tools** link opens the processor
workbench. Search supports lexical retrieval without embeddings. Chat and report
tiles require saved text and a configured AI model; Topic Explorer requires
current compatible embeddings and can explore a partially indexed library.
Gray tools show what is missing. A configured model is not a connection test.

Setup appears until **Done with setup** is saved for this library. Hosted Setup
is administrator-only. It remains accessible in the sidebar after dismissal.
`GET /api/workbench/home` supplies metadata-only readiness;
`POST /api/admin/setup/dismiss` persists dismissal (administrator and CSRF checks
apply on the hosted service). Home does not read source text, load vector payloads,
compute projections, or invoke models. Shared tile/navigation definitions and
UI components consume product adapters; they do not access storage directly.


### Shared Tools and Setup screens

`/tools` is the document-tool landing page, using the Home tiles and readiness
contract. Library-wide operation selection and saved results remain at
`/tools/workbench`, linked as **Open processing workbench**.

Local and hosted Setup share `SetupLayout`, `CapabilitySection`, and
`ReadinessPanel`: model connections, four OSII component drawers, and advanced
diagnostics. Product adapters retain their own persistence and permissions.
Hosted source selection stays inside the read-only mounted root; local file-type
routing and launcher lifecycle controls remain local capabilities. Registering a
Processor API address never installs or starts it.
