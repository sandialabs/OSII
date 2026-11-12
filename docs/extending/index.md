# Extend OSII

For retrieval, reranking, or iterative question-answering ideas, use the
[Core RAG strategy authoring guide](rag-strategies.md). RAG extensions are separate
from the four processor kinds below.

An OSII processor is a small HTTP service that performs one specialized task.
It receives a self-contained, validated request and returns grounded text or a
standard artifact. It never writes directly to the OSII store.

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
6. Package the service in a container.
7. Paste its base URL under **Setup → Advanced & diagnostics → Register running processor**.
8. Use **Health** to test liveness and **Test** to validate the v1 contract.
9. Run it against an ingested file and inspect the result in the dashboard.

When developing both services on the host, register a loopback base URL such
as `http://127.0.0.1:8091`. When the OSII API is packaged, use a Compose service
name for another service on the same network, or `host.containers.internal`
for a processor running on the host. Enter only the base URL; OSII appends the
health, descriptor, and operation paths.

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


## Shared workbench layout

Local and hosted products use `src/app/layout/WorkbenchLayout.tsx`,
`WorkbenchNavigation`, and `HeaderBar` for the responsive shell. Supply navigation
items, the selected item and a navigation callback; product routing and role
filtering stay in their adapters. Optional actions/footer hold hosted account
controls. Shared layout components never call Core, inspect accounts or access a
filesystem. Local keeps its `app/tools.tsx` route registry; hosted Setup and its
legacy bookmarks are handled in `features/server/Workspace.tsx`.

`features/files/components/FileGrid.tsx` is the common flat document view, with
bounded card rendering, thumbnails, filename/path filtering and sorting. Hosted
adapters supply file-card models plus optional `selectedIds`/`onToggle` controls;
shared file widgets never infer processing success from the deployment mode.
Folder Browse, search results, Topic Explorer, document panes and processing
activity continue to use their respective shared widgets. A transport-specific
feature needs a Core adapter; copying a local filesystem call into hosted UI is
not a supported extension method.

Hosted inventory uses the same `domain/processing/directory_scan.py` enumerator
and `directory_browse.py` cursor reader as local. Only their Core storage and
queue coordinators differ: local `volume/scanner.py` persists the separate SQLite
inventory; hosted `persistence/inventory.py` and `server/inventory.py` persist
PostgreSQL observations and use leased worker jobs. Never import the local
SQLite coordinator or filesystem sidecar store into a hosted adapter.

The shared `DiscoveryIntakePanel`, `DiscoveryActivity`, `LocationBrowser`,
`ToolsPage`, `ToolActionPanel`, `ScopePicker`, product editors and
`ScopeOverviewPanel` consume Core contracts. Hosted adapters enforce mount
containment, sessions, CSRF, roles and private collection visibility. Optional
capability fields disable unavailable actions; local remains account-free.
`configureApiClient` supplies hosted transport headers at composition time.
New library-wide methods use the existing synthesizer/enricher SDK descriptors
and standard artifacts; they do not require a new processor component kind or a
custom dashboard page. See the [server runbook](../operations/runbook-server.md)
for snapshot limits and processing permissions.


Whole-scope processing uses the shared `domain/processing/scope_batches.py`
engine and `BatchStorage` protocol. The request boundary is bounded while the
corpus has no fixed document or total-text cutoff. Follow the
[batch contract](../reference/processor-api/enrichment.md#whole-scope-batches)
when adding a tool: preserve every supplied text window, return relative
citations, and declare whether derived wiki summaries can be combined. The
shared `ScopeBatchResults` component loads result metadata by page and opens
individual results on demand.


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


### Toolbox and processor terminology

The **Toolbox** is the frontend collection of tools such as Browse, Search, Chat,
reports, library analysis, and topic exploration (`/tools` remains its URL).
Backend components are **processors**, implementing extraction, synthesis,
embedding, or enrichment. Their independent source modules live under
`osii-processor-modules/`; existing processor IDs and saved provenance are retained.

Browse uses the same `BrowseExplorer`, `BrowseGrid`, breadcrumbs, and folder-detail
components in local and hosted products. Adapters own catalog queries and URL
state; hosted source files stay read-only. List/icon views, name filtering and
sorting apply to the current folder; server catalogs remain paginated.
