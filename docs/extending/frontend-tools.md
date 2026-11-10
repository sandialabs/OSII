# Extend the Workbench frontend

Start by deciding whether the extension is a **method**, a **product view**, or
a **workspace**. Most better implementations need only a method. Core owns
canonical persistence, scopes, model access, runs, and provenance; the browser
uses Core HTTP APIs and never opens sidecars or calls a provider directly.

## Add an interchangeable method

Implement the existing [Processor SDK](processor-development.md) descriptor and
operation. Register the running service in **Setup → Advanced & diagnostics →
Custom Processor API services**. Declare supported `scope_types`,
`output_kinds`, `model_requirements`, and `config_schema` accurately.

- An **extractor** appears in Intake's reading methods and file-type routing.
  Return canonical text segments/source artifacts. An alternative OCR engine
  needs no OCR-specific sidebar page.
- A **synthesizer** or **embedder** appears in the corresponding Intake step.
- An **enricher** appears in scope tool controls and **All tools**. Declare
  `wiki_markdown` for the shared wiki workflow or `document_metadata` for
  metadata suggestions. `topics`, `embedding_projection`, and `recommendations`
  declare separate topic-modeling, projection, and recommendation operations.
  Other output kinds use Analyze. Tables, entity
  lists, graphs, and wikis reuse their existing viewers.

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
"generating" toast. See the [workbench decision](../concepts/adr-workbench-tools.md)
for exact limits, retry semantics, and remaining legacy paths.

To introduce a new operation grouping, update the catalog's descriptor-to-action
adapter and the catalog label mapping. No new Processor SDK kind is needed.
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
4. Register a lazy page once in `src/app/tools.tsx` with a unique ID, path,
   short label, icon, and group (`documents`, `tools`, `start`, or `setup`).
   Routing and sidebar consume that registration. Parameterized detail routes
   belong in the router and use `ToolBoundary`.
5. Put shareable scope and selection in the URL. Use `buildFileRoute` for
   existing file identities. Keep drafts separate from saved products.
6. Handle loading, empty, partial, unavailable, stale, and error states. Provide
   keyboard alternatives for graphical selection. Put detailed explanations in
   Options/Details and keep status/error recovery beside the relevant action.

This is build-time registration of reviewed code, not arbitrary downloaded JS.
The hosted branch separately enforces its persistence and account permissions.

## Topic Explorer as a reference

`/topics` uses typed adapters and query hooks over Core's
`domain/services/topics.py`, through `api/topics_routes.py`:

| Endpoint | Inputs | Result |
| --- | --- | --- |
| `POST /api/topics/map` | Scope; limit 1–500 | Active index identity/model, coverage counts, document projection, explained variance |
| `POST /api/topics/related` | Scope, document ID; limit 1–50 | Related documents ranked in full embedding space with cosine similarities |

The map averages normalized chunk vectors per document and uses centered PCA
with stable axes. Axes are not inferred topic labels; scores are not confidence.
A filename filter affects the displayed map, not related ranking. Counts disclose
unindexed/stale documents and the stable displayed subset. Projection caches
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
