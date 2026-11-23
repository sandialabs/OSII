# OSII architecture

OSII separates evidence, computation, and presentation. Core owns validation,
provenance, durable work, and persistence. The dashboard and optional agent tools
are clients. Processors compute a result for an explicit request.

```text
Dashboard / Python / optional MCP
                |
                v
        Core API and worker
          |             |
          v             v
   library storage   Processor API services
                     extract / synthesize / embed / enrich
```

## Delivery profiles

`main` is the shared development branch. The default dashboard build serves
OSII Dev and the Windows installer. The hosted dashboard build selects the
server shell, which supplies sign-in, account navigation, and role-aware actions.
Both shells use shared views for document browsing, collection fields, and other
workbench tools. Hosted API routes independently enforce access and use hosted
PostgreSQL. The desktop runtime owns a private loopback API and uses sidecars.

Desktop and hosted artifacts can release on different schedules. Record the
source commit for each build and apply shared fixes to `main` once. Run the
local, hosted, and Windows delivery checks for shared changes.

## What is stored

Original documents are read in place and remain unchanged. Extracted text,
source locations, processor identities, and derived products retain provenance
so a person can inspect the evidence behind a result.

| Data | Owner and role |
| --- | --- |
| Local library | Portable `.osii` sidecars by default; optional explicitly initialized PostgreSQL |
| Hosted library | PostgreSQL, accessed only by Core and its worker |
| File inventory | Separate canonical SQLite database on the owning machine's local disk |
| Search indexes and sidecar catalog | Derived caches that can be rebuilt |
| Summaries, wikis, and other generated products | Saved outputs with input provenance and revision history |

The inventory database is not a sidecar cache. Rebuilding a catalog must never
replace it. Switching a local library to PostgreSQL requires explicit schema
initialization and a non-destructive import; startup never migrates it silently.
See [local storage](../reference/local-storage.md),
[store layout](../reference/osii-store.md), and
[inventory recovery](../operations/large-volumes.md#backups-schema-changes-and-scale-checks).

## Processing

Intake freezes selected files and processing choices, then queues durable work.
Core validates returned results and commits them. Pause, cancel, resume, and
retry operate at safe stage boundaries; committed work is retained.
A lost model response can still cause a repeated request on retry.

There are four processor kinds:

| Kind | Input | Output |
| --- | --- | --- |
| Extractor | One document's explicit bytes | Text segments, source locations, source artifacts |
| Synthesizer | Supplied text and evidence | Cited narrative or preview |
| Embedder | Identified text chunks | Vectors with model and dimension metadata |
| Enricher | A bounded document or scope snapshot | Typed tables, graphs, entities, wikis, or other artifacts |

Processors expose `/health`, `/v1/descriptor`, and one kind-specific operation.
They never browse the corpus or write library storage. Descriptors declare
supported inputs, scopes, outputs, model requirements, and settings.
Core validates schemas and provenance and assigns canonical storage paths.

Use the [Processor SDK](../reference/processor-api/index.md) to call and test a
processor directly in Python, then expose the same implementation over HTTP.

## Search and grounded chat

Core owns retrieval, scope enforcement, optional reranking, context assembly,
and answer citations under `osii/rag/`. Keyword search works without a model.
Semantic retrieval needs a matching embedding model and index; vectors from
different model spaces must not be combined.

The browser calls Core rather than a model provider. Chat returns the actual
retrieval mode and provider used. Experimental comparison and iterative modes
have explicit limits; their traces aid inspection and do not prove answer
quality. See [RAG strategies](../extending/rag-strategies.md) and
[search semantics](../reference/api/search-semantics.md).

## Code and extension boundaries

| Location | Responsibility |
| --- | --- |
| `osii-core/osii` | Domain services, storage, API, workers, and grounded chat |
| `osii-core/osii/processor_sdk` | Public request/response contracts and service helpers |
| `osii-core/services` | Baseline local processor hosts and model-provider bridge |
| `osii-processor-modules` | Independently deployable processor implementations |
| `osii-dashboard/dashboard` | Browser workflows and shared artifact viewers |

A frontend **Toolbox** item is a workflow. A backend **processor module** supplies
computation. Existing artifact formats and shared controls let several methods
serve the same workflow without a new page for each processor. Frontend
components receive typed API data; storage, credentials, and hosted permissions
stay behind Core adapters.

The `osii-demo-notebooks` and `osii-mcp` branches contain independent optional
downloads. They install Core as a dependency and do not carry another application
source tree. MCP currently accesses local sidecars through Core's Python
interfaces; it is not a hosted account/permission adapter.

## Local and hosted applications

`main` supports local files without user accounts. The `osii-server` branch
provides shared PostgreSQL storage and hosted authentication. The
`osii-standalone` branch packages the local application for Windows.
Shared domain and UI code uses product-specific storage and transport adapters.

Read the [library read contracts](../reference/library-reads.md),
[processing commits](../reference/processing-commits.md),
[authoring interfaces](../reference/library-authoring.md), and
[retrieval and jobs](../reference/retrieval-jobs.md) when changing those boundaries.


## Beta processing flows and queue

The beta UI separates setup, intake, queue diagnostics, and collection maintenance.
A named flow in `processors.toml` declares ordered extension rules and reader
fallbacks, synthesis/enrichment methods, and embedding chunk settings. Setup tests
sample operations and records a configuration fingerprint; Intake selects one
flow and runs all stages. File selection does not resolve routing or invoke models.
Queued SQLite payloads snapshot reader order and resolved request settings;
workers and retries use those snapshots. Editing a flow affects later jobs.
Existing embedding identity checks and checkpoints still protect vector reuse.

The durable local queue remains the execution boundary. This change adds no broker
or external queue dependency. The queue UI shows operational evidence and copyable
errors; generated products belong to Files and Collections. Collection reprocessing
uses an explicit collection-scoped endpoint and the same worker.

Large-volume discovery is preserved on `archive/large-volume-discovery-2026-11-19`.
The beta main launcher omits its worker and rejects inventory writes, while leaving
historical evidence readable. This is a presentation/lifecycle reduction, not an
inventory schema migration or a deletion of canonical data.
