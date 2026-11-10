# ADR: Shared Core workflows and selectable persistence

Date: 10 November 2026

Status: Accepted direction. Shared reads, document commits, and aggregate product
commits and initial product-authoring/collection interfaces are implemented; broader adoption, backend selection, and
migrations remain staged work.

## Context and current behavior

OSII-local and OSII-server share Processor API contracts and frontend components,
but do not yet provide interchangeable persistence. Local workflows frequently
accept an `.osii` path and read or write files directly. Server workflows use
PostgreSQL, with a partial `LibraryStore` interface whose whole-library snapshots
are unsuitable as a general large-library query interface.

Local currently has several distinct stores:

| Store | Responsibility |
| --- | --- |
| Canonical `.osii` files | Text representations, provenance, artifacts, and collection records |
| Sidecar catalog SQLite | Rebuildable metadata projection of canonical sidecars |
| Inventory SQLite | Canonical file inventory and selected-processing records owned by `osii.volume` |
| Jobs SQLite | Durable operational state for sidecar processing |
| Search indexes | Derived lexical and vector retrieval structures |

The inventory is not a sidecar catalog. It cannot be reconstructed by rebuilding
that catalog, and its selected-processing results are not automatically part of
sidecar search. The local branch documents this in
`docs/concepts/adr-volume-store.md` and `docs/operations/large-volumes.md`.

The server already keeps documents, extractions, chunks, artifacts, collections,
settings, jobs, and accounts in one PostgreSQL database. Equivalent metadata
inventory integration remains future work. Having separate domain responsibilities
does not require separate databases.

## Decision

### Four responsibilities over shared persistence boundaries

| Responsibility | Owns | Extension boundary |
| --- | --- | --- |
| Work management | Scheduling, dependencies, resource limits, checkpoints, recovery, progress, pause/cancel, and retry | Core job execution and job-store interfaces |
| Processing | Extraction, synthesis, embedding, and enrichment | Existing Processor SDK/API |
| Authoring | Human corrections, saved revisions, activation, lineage, and edit conflicts | Core authoring operations and reusable editors |
| Exploration | Browsing, search, grounded chat, and artifact/topic views | Core query APIs, shared UI components, and Workbench registration |

Core resolves scopes, supplies bounded inputs, validates processor responses,
and commits results. Processor implementations do not browse a corpus or write
its store. Chunking, retrieval, reranking, and bounded iterative RAG remain Core
responsibilities rather than additional processor kinds.

Exploration contributors use document, representation, and artifact identifiers
through Core APIs. They do not need filesystem paths, SQL access, or provider
credentials. Standard artifacts use existing renderers; specialized views use
the Workbench extension mechanism (documented in local's
`docs/extending/frontend-tools.md`), currently reviewed source registered at
build time. Editing is a Core capability, even
when initiated from an exploration view.

Use small typed Python interfaces inside the existing Core for document reads
and commits, artifacts/collections, retrieval, and jobs. Source access remains
an explicit separate edge for opening originals. Do not create a universal
store abstraction containing accounts, processing, filesystem operations, and
every query. Storage adapters may share a database connection without sharing
all their public responsibilities.

### Select the backend at startup

The target local configuration is `OSII_STORAGE_BACKEND=sidecar` by default or
`OSII_STORAGE_BACKEND=postgres` with `DATABASE_URL`. These are **planned settings**;
adding them to today's `.env` does not switch storage. Selection will happen at
process startup, with the same selection supplied to API, workers, Python entry
points, and MCP. It will not require a different build. PostgreSQL dependencies
will be optional for the normal local installation.

Local operation stays on loopback without user accounts or login, including
when PostgreSQL is selected. Hosted authentication and permissions remain
server responsibilities. The server requires PostgreSQL; it never falls back
to files. Backend selection does not enable hosted startup or authentication.

The hosted target uses one application PostgreSQL database, including inventory
and jobs. Local PostgreSQL mode should likewise use one application database
once those adapters and their explicit migrations are implemented. Existing
canonical inventory SQLite remains unchanged until that dedicated migration is
implemented and verified. Do not temporarily route its records through sidecar
catalog rebuild or corruption recovery.

### Preserve meaning across adapters

Shared contracts must preserve source locations separately from content hashes,
document/representation identities, exact text and citation spans, geometry,
scope membership, processor configuration, model identity, and output lineage.
Queries must support bounded scope filtering and pagination rather than require
whole-corpus snapshots. Backends may implement different retrieval indexes while
returning the same evidence contract and accurate retrieval-method metadata.

A commit exposes a complete validated result and supports idempotent retry.
PostgreSQL uses transactions; the sidecar adapter needs a documented staged
commit and recovery boundary. Atomic replacement of individual files alone
does not establish a multi-file transaction. Derived catalog/index maintenance
must not become the only authoritative copy of committed results.

### Save revisions, then activate

Human edits to extracted text, syntheses, or wiki Markdown save a new revision
linked to its input revision. Saving does not select that revision for downstream
processing. A separate activation selects it as preferred and marks dependent
outputs stale without deleting them or automatically invoking models.

Preserve original evidence and earlier revisions. Editing requires stale-write
checks; citations identify the representation revision as well as text offsets.
Original OCR geometry is retained with its extraction and is not invented for
newly written text. The initial authoring contract covers text/Markdown;
arbitrary graph or table editing requires its own typed commands. Existing local
segment and whole-text edits must migrate deliberately; server metadata edits
do not establish equivalent text-editing support.

### Keep durable database queues first

Retain local and PostgreSQL job persistence behind a shared execution contract.
Specify per-step checkpoints, worker ownership/leases, bounded retries, priority,
resource-aware concurrency, observable progress, and cooperative pause/cancel.
Retries may repeat an external model call after a lost response; idempotent
commits must prevent duplicate canonical results.

Do not add a broker or workflow platform in this refactor. RabbitMQ could later
distribute task notifications, but does not replace OSII's progress, lineage,
checkpoint, or commit rules. Prefect and Temporal are possible future evaluations
for more complex orchestration; no vendor or additional service is selected.

### Backend selection and data transfer are separate

Selecting a backend opens its existing library; it does not silently import,
synchronize, or dual-write another store. Backend failure reports unavailability.
Migration is explicit, non-destructive, and preserves IDs, revisions, provenance,
artifacts, collection membership, and handling labels. Source paths can be
remapped explicitly. Credentials and hosted accounts are not portable library
content. Search indexes can be rebuilt for the destination.

## Implementation sequence and acceptance

1. **Shared document and artifact reads: initial slice implemented.** The
   [read-interface reference](../reference/library-reads.md) documents the
   adapters, compatibility mappings, limitations, and real PostgreSQL tests.
   The slice covers metadata, preferred/explicit representations, document
   artifacts, and scoped pagination. Broader workflow adoption remains incremental.
   Typed document summaries, representation records, artifact descriptors, and
   paginated results cover scoped document listing, document lookup,
   representation/segment reads, and artifact listing/content access. Existing
   sidecar readers and PostgreSQL operations supply these interfaces without
   moving data. Compatibility mappings preserve existing REST response shapes.
2. **Validated processing commits: document and aggregate product slices implemented.** See
   [processing commit contracts and guarantees](../reference/processing-commits.md)
   for adapter adoption, retry/lease behavior, and the distinction between an
   atomic product and a resumable multi-product step. Reuse storage-independent SDK processors;
   adapt legacy store-aware implementations at the Core boundary. Define one
   commit operation for each completed processing result and verify crash/retry
   behavior before transferring additional workflows.
3. **Authoring and collections: initial product/collection slice implemented.**
   [Shared authoring contracts](../reference/library-authoring.md) provide draft
   save/activation, conflicts, and collection metadata/membership commands over
   existing storage. Product editors retain immediate activation for compatibility.
   Legacy document-text overrides and extraction versions remain unchanged;
   their shared authoring/migration work is still explicit future work.
4. **Retrieval and jobs.** Supply bounded retrieval to shared RAG workflows and
   converge job controls/checkpoints. Preserve hosted authorization before
   evidence selection or processor dispatch. Keep current search backends until
   benchmarks justify a change.
5. **Local PostgreSQL selection and transfer.** Wire the startup setting and
   optional dependencies only after the required adapters pass. Add explicit
   transfer and inventory migration with backup, verification, and recovery;
   preserve source stores. Keep ordinary `make dev` and PowerShell startup simple.

Shared changes are focused commits transferred between the local and server
branches. Do not merge hosted authentication, database migrations, or startup
into local implicitly. No new top-level package, service, or startup menu is
needed for these boundaries.

The acceptance gate for this slice is the same read-contract tests passing against
temporary sidecars and a real isolated PostgreSQL test database: scoped/cursor
listing, empty/missing records, representation text/spans/geometry, and standard
artifact content. Document/artifact inspection must preserve API compatibility
and shared UI behavior. Reads must not initialize or mutate canonical content;
legacy registration happens explicitly rather than as a side effect of lookup.

Later gates cover partial writes, repeated commits, stale revisions, activation
without model calls, job recovery/controls, authorized hosted scope filtering,
secret-free transfer, and preservation of canonical inventory. Use generated
fixtures, never migrate a user's library for a test. Benchmark realistic 10,000-
and 100,000-document workloads before claiming supported capacity; row counts
alone do not establish throughput or memory limits.

## Consequences

The two deployments can share workflow logic while keeping appropriate storage
and identity adapters. Human edits become durable authored records with explicit
lineage. Contributors can build processors and views without learning both
persistence implementations. Compatibility and recovery contracts add work, but
the staged approach keeps current libraries and startup behavior intact while
each boundary is proven. This decision records the plan; it does not implement
the backend setting, editing model, queue consolidation, or migrations.
