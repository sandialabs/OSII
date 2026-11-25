# Extend the Workbench frontend

Start by deciding whether the extension is a **method**, a **product view**, or
a **workspace**. Most better implementations need only a method. Core owns
canonical persistence, scopes, model access, runs, and provenance; the browser
uses Core HTTP APIs and never opens sidecars or calls a provider directly.

## Design each view around one action

Name the **scope** (one file, a folder, a collection, or the library) and the
**primary action** (read, search, edit, run, or review). Make the action order
clear through layout, short headings, and the controls themselves. Use a
labeled question-mark button for optional explanation and show errors beside the
action they affect. Avoid nested drawers and repeated instructions.

Use the shared product vocabulary in `src/domain/libraryProducts.ts` and the
`LibraryFlow` component to show what a tool **reads** and **writes**. List saved
outputs in the relevant file or collection view. Use a dedicated workspace for
running processors and reviewing their progress.

| Library data | Where to find it |
| --- | --- |
| Original and file facts | Files, under Source |
| Extracted text, corrections, and versioned extraction artifacts | File products, under Extracted text |
| Document metadata, summaries, wikis, and other derived artifacts | File products or the owning scope |
| Collection membership | Collections |
| Report drafts | Create a Report, with browser drafts and export |
| Search chunks and embeddings | Search and Topic Explorer use the index; Library Overview shows coverage |
| Run status, errors, and logs | Intake & Queue |

Core owns storage. OSII-local saves library products in sidecars by default.
The PostgreSQL profile exposes the same products through Core. Preserve source
identity and provenance across processors, edits, and deployments.

### Declare compatible inputs

A workspace that consumes saved products declares its required product kinds
and scopes. For example, Topic Explorer needs compatible embeddings and works
across original file types. A workspace that works on source bytes declares
`input: "source"` and uses the selected processor's supported file types to
validate the file before enabling its action. Declare `capabilities.file_extensions`,
including the leading dot, or `capabilities.media_types` on the Processor API
descriptor. Extensions take precedence when present. MIME-only declarations
accept exact types, `image/*`-style patterns, or `*/*`. OSII infers MIME
from filenames during browsing. Core checks the descriptor again at execution.

OCR Workbench is the reference workspace. An OCR extractor opts in with
`"ocr_text"` in `capabilities.output_kinds` and declares its supported formats.
It returns the normal extraction response, with page, regions, and confidence
when available. One workspace can offer several OCR methods. Selecting and
opening a file never starts a run. Run OCR saves a new version and preserves
the current primary text for existing documents. The first successful
extraction of a new file becomes its primary text.

## Add an interchangeable method

Implement the existing [Processor SDK](processor-development.md) descriptor and
operation. For a backend module, add its [manifest](processor-modules.md); local development
discovers it automatically. Hosted administrators register independently deployed
services in Setup. Declare supported `scope_types`,
`output_kinds`, `model_requirements`, and `config_schema` accurately.

- An **extractor** appears in Intake's reading methods and file-type routing.
  Return canonical text segments/source artifacts. An alternative OCR engine
  needs no OCR-specific sidebar page.
- A **synthesizer** or **embedder** appears in the corresponding Intake step.
- An **enricher** appears in the **Toolbox**. Declare `wiki_markdown` to appear in
  the **Create a wiki** method selector or `document_metadata` for **Suggest
  metadata**. Other registered scope methods get their own Toolbox entry and
  share the scope picker and run controls. Tables, entity lists, graphs, and
  wikis use the existing product viewers.

Core's catalog at `GET /api/enrichment-jobs/tools` returns the operation,
method identity/version, scopes, configuration schema, compatible model choices,
effective bindings, execution path, and limits. The catalog groups computation;
`src/app/tools.tsx` registers navigable workspaces. Do not conflate the two.

`ToolActionPanel` supplies method selection, schema-driven Options, an actual
writing-model default, durable submission, errors, retry, and progress.
`ScopePicker` supplies named library/folder/collection/document selection.
`ScopeWikiPanel` and `ScopeEnrichmentsPanel` show saved outputs for each scope.
Reuse these components instead of making a new job form for each service.

Scope tools submit to `POST /api/enrichment-jobs/run` with `enricher_name`,
`scope`, optional `enricher_config`, and optional `model_bindings`. Omitting a
binding keeps the configured tool choice; an empty capability binding explicitly
inherits a library default. Core validates before queueing and freezes bounded
inputs. Poll `/api/runs/{run_id}`; a submission acknowledgement is not completion.
Use the existing run control endpoints and Activity rather than a temporary
"generating" toast. See the [Workbench architecture](../concepts/architecture.md) and branch API
reference for limits, retry semantics, and permission boundaries.

Add a dedicated route in `src/app/tools.tsx` when a task needs a specialized
interaction. Use the existing Processor SDK kinds and the capability catalog.
Topic inference, vector projection, and similarity ranking are separate actions;
a projection must not be presented as a named-topic model.

## Add a new product visualization

Prefer the [standard formats](../reference/processor-api/standard-artifacts.md).
`EnrichmentArtifactView.tsx` contains the reviewed `artifactRenderers` registry.
A method returning an existing format needs no new registration. A new format
requires a typed SDK contract, response validation, an API type, and one renderer
registration. Keep sorting/export/navigation local to the viewer. Preserve
provenance and provide an inspectable fallback for unfamiliar JSON.

All standard wikis use `WikiProductEditor`: Read, Edit, History, and comparison.
Other saved JSON products, summary text, and legacy bundle text/Markdown use `DerivedProductEditor` with the
same revision contract. Structured products edit validated JSON; metadata has a
field form in `SuggestedMetadata`. Extraction products offer an editable copy
while retaining immutable original evidence.
The revisions adapter lives in `src/api/tools.ts`; Core owns conflict detection
and generated candidates. Do not overwrite an artifact directly from a custom
editor or claim that edited passages retain validated citation spans.

## Add a workspace

1. Put its page under `src/features/<feature>/`. Use shared API adapters,
   scope controls, file-route helpers, and viewers.
2. Define typed HTTP adapters in `src/api/`. Use relative `/api/...` URLs and
   `apiJson`; keep persistence logic in Core domain services.
3. Include scope, selected document, method/configuration, and relevant index
   identity in query keys. Forward cancellation signals where supported and
   avoid displaying results from a previous scope as current results.
4. On local, register a lazy page in `src/app/tools.tsx` with a unique ID, path,
   short label, icon, and group (`documents`, `tools`, `start`, or `setup`).
   Register the scope, source or saved-product input, and read/write flow for
   Toolbox tiles in `src/domain/workbench.ts`.
   Routing and sidebar consume that registration. Parameterized detail routes
   belong in the router and use `ToolBoundary`.
5. Put shareable scope and selection in the URL. Use `buildFileRoute` for
   existing file identities. Keep drafts separate from saved products.
6. Handle loading, empty, partial, unavailable, stale, and error states. Provide
   keyboard alternatives for graphical selection. Keep status and recovery
   beside the action and use a labeled question-mark button for optional help.

This is build-time registration of reviewed code, not arbitrary downloaded JS.
The hosted branch separately enforces its persistence and account permissions.

## Topic Explorer as a reference

For the shared view registry, circle selection, collection review and advanced
metadata contract, see [Topic Explorer extensions](topic-explorer.md).

`/topics` uses typed adapters and query hooks over Core's
`domain/services/topics.py`, through `api/topics_routes.py`:

| Endpoint | Inputs | Result |
| --- | --- | --- |
| `POST /api/topics/map` | Scope; optional positive limit (default: all) | Active index identity/model, coverage counts, document projection, explained variance |
| `POST /api/topics/related` | Scope, document ID; limit 1–50 | Related documents ranked in full embedding space with cosine similarities |

The map averages normalized chunk vectors per document and uses centered PCA
with stable axes, using a bounded approximate fit for larger datasets. Axes are not inferred topic labels; scores are not confidence.
Search covers every mapped document; the default map includes the full indexed
scope. Counts disclose unindexed/stale documents. An explicit API limit affects
returned points only, never the fit; related ranking always uses the full space. Projection caches
are keyed by index and scope evidence; they do not become canonical products.
Neither endpoint builds embeddings or calls a model. Missing/incompatible or
changing indexes return actionable errors. The page supports point/list
selection, pan/zoom, scope changes, URL selection, and opening original file
views. See **How the map works** for the interpretation limits.

## Verify

Run focused Core/SDK tests for the contract and persistence changes. Run
`npm test` and `npm run build` in `osii-dashboard/dashboard`. Browser-check normal,
empty, failed, restarted, and stale-result flows. For wiki changes verify draft
recovery, conflicting edits, and regeneration after a human edit. A new method
returning an established format should work without feature-specific UI edits.

`make dev` (Windows: `.\scripts\osii.ps1 dev`) reloads Core and Vite; refresh
after route registry changes. Production assets require a dashboard rebuild.


## Text presentation and editing

Use `components/text/MathpixText` for extracted or derived Markdown. It renders
Mathpix Markdown locally, including LaTeX mathematics and tables, and always
provides a Plain text mode. The raw string remains the stored value. Do not add
a renderer per extractor or send documents to a rendering service. Untrusted
markup runs in a reusable Web Worker with cancellation and a 12-second timeout;
source HTML is disabled and final HTML/SVG is sanitized before insertion.
Text views page at 40,000 characters; the grounded editor mounts at most 20
segments. A markup block split at a section boundary may need Plain text.

Use `/api/products/revisions` to save human products with `expected_revision`.
Conflict responses preserve browser drafts; generation after an edit adds a
candidate. Keep metadata overlays distinct from filesystem facts and extracted
text. Original-source offsets always name their representation; a rendered DOM
position is never an original-file character span.

The pinned Mathpix browser bundle contains older transitive parsers with upstream
npm audit advisories. Disabling source HTML, linkification, and typography avoids
the affected optional parsing paths; bounded worker execution and final DOMPurify
sanitization remain required. These controls are not a claim that upstream
advisories are resolved. Do not move parsing back onto the UI thread or enable
source HTML in a custom view without reviewing that boundary.


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

## Frontend Toolbox versus backend modules

A Toolbox item is a React workflow: a page, route, scopes, controls, and result
views. A processor module is the Extractor, Synthesizer, Embedder, or Enricher
that performs computation. One Toolbox item can offer several interchangeable
processors; one processor can serve several pages. A manifest never loads
arbitrary JavaScript into the browser.

A collection data card generator usually starts as an Enricher module returning
a standard artifact. Its descriptor adds a method to the processing controls;
existing viewers can display standard tables, graphs, Markdown, or inspectable
JSON. It needs no dedicated page just to become usable.

For a dedicated workflow, place the component under `src/features/<name>/`.
Local routing and sidebar entries use `src/app/tools.tsx`. Shared Toolbox/home
tiles and navigation labels use `src/domain/workbench.ts` (`documentTools` and
`workbenchNavigation`) and `src/app/layout/workbenchNavigation.tsx` (icons).
For a shared tile, also supply the local page loader and hosted adapter:
`src/features/server/Workspace.tsx` owns hosted `pagePaths`, rendering, and
role-gated navigation. Preserve server authorization in its API adapter;
OSII-local remains authentication-free. Add readiness behavior and tests if the
new tile needs prerequisites. Do not advertise a tile before its route and both
product adapters are implemented.

Local Toolbox routes get a breadcrumb back to Toolbox through the route
registry. Use `PageBreadcrumbs` on nested views with a named parent, such as
`Collections → Collection name → Wikis`, or a parent section with a stable
anchor, such as Setup’s Processors list. Link each parent to its canonical
destination so the trail works when opening a bookmark. Use tabs for modes
within the same task, such as reading, editing, and comparing wiki revisions.

Run dashboard tests and build on each affected branch, plus
`python scripts/check_extensions.py`. Keep durable processing and result storage
behind Core APIs; reuse ScopePicker, ToolActionPanel, and standard artifact viewers.
