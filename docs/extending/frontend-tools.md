# Extend the Workbench frontend

A Workbench tool is a routed React feature that uses Core's HTTP API. It is
different from a Processor API service: a processor computes bounded outputs;
a tool helps a person work with Core-owned documents and artifacts. Adding a
frontend tool does not require a new service, processor kind, or persistence
implementation.

## Architecture review

The dashboard already separates API adapters, TanStack Query hooks, feature
pages, and pure presentation/domain helpers. Core owns scope membership,
storage, model connections, and processing. Keep that boundary: browser tools
must not read `.osii`, connect to databases, or call model providers directly.

This review addressed three extension weaknesses:

| Finding | Change |
| --- | --- |
| Routes and sidebar entries were maintained separately | `src/app/tools.tsx` is the typed registration shared by routing and navigation. |
| Every top-level page was imported eagerly | Registered pages and document/collection detail pages now load on demand. The explorer's rendering code is absent until needed. |
| A module load/render failure could remove the entire workbench | Each route has its own Suspense loading state and error boundary; the sidebar remains usable. API errors belong to feature-level states. |

This is a build-time extension mechanism for reviewed source code. It does not
download arbitrary plugins or provide security isolation for untrusted code.
Existing providers remain shared infrastructure; feature state stays local or
in scoped query caches. No new frontend or Python dependencies were needed.

## Add a tool

1. Put the page and tool-specific components under `src/features/<tool>/`.
   Keep components independent of other feature pages; reuse public API
   adapters, route helpers, and genuinely shared components instead.
2. Define the HTTP contract in `src/api/<tool>.ts`. Reuse `apiJson`, relative
   `/api/...` URLs, and the existing `ScopeDescribeRequest` union. Keep
   tool-specific response types with the adapter rather than growing a
   process-wide context or duplicating document identities.
3. Add a feature-local query hook. Include all request inputs, including scope,
   selected document, and relevant index identity in its query key. Forward
   TanStack's `AbortSignal` to the adapter so obsolete requests can be cancelled.
   Do not use placeholder results from a previous scope.
4. Export a named page and register it once in `src/app/tools.tsx`:

   ```tsx
   {
     id: "my-tool",
     path: "/my-tool",
     label: "My tool",
     group: "documents",
     icon: MyToolIcon,
     Page: lazy(() => import("../features/my-tool/pages/MyToolPage")
       .then(module => ({ default: module.MyToolPage }))),
   }
   ```

   Import the icon and use unique IDs and absolute paths. The router and
   sidebar consume this descriptor automatically. Register parameterized
   detail routes explicitly in the router and wrap them in `ToolBoundary`.
5. Use URL search parameters for shareable selection/scope and React state for
   transient controls. Clear selections when scope changes. Link to existing
   file views with `buildFileRoute`; preserve Core file IDs and source paths.
6. Handle loading, empty, partial, unavailable, and error states. Keep displayed
   counts accurate, expose retry/refresh, and label approximate/model-backed
   results. Provide a keyboard-accessible equivalent for graphical selection.

If new server behavior is required, add a thin FastAPI route over a Core
domain service, validate inputs, and apply existing scope membership rules
before deriving results. Keep filesystem and vector formats inside Core. In
the hosted branch, the same API contract also needs that branch's account and
permission enforcement; copying local routes alone is insufficient.

## Topic explorer reference implementation

Open **Topic explorer** (`/topics`). Select all documents, a collection, or a
folder. Filter mapped filenames/paths, select a point or list item, follow
**Explore related**, and use **Open** for the existing document viewer. Drag
to pan and use the zoom/reset buttons. Scope and selected file live in the
URL; **Refresh** rereads the active index. A filter affects the displayed map,
not the scope used for related-document ranking.

The page uses a feature-local hook and typed topic API adapter. Core's
`domain/services/topics.py` computes results; `api/topics_routes.py` validates
and transports them. Processors and frontend components never open FAISS.

### HTTP contract

| Endpoint | JSON input | Response |
| --- | --- | --- |
| `POST /api/topics/map` | `scope` (default root), `limit` (1–500, default 500) | Index identity/model/dimensions/semantic flag, scope/indexed/stale/unindexed/shown counts, projection and explained variance, document points. |
| `POST /api/topics/related` | `scope` (default root), `file_id`, `limit` (1–50, default 12) | The same index identity, selected document, and related documents with cosine similarities. |

Both use root, folder, collection, or object scopes. Folder/collection/object
scopes require their existing IDs. Unknown scopes yield no members; an
unavailable selected document yields HTTP 409. Invalid request shapes return
422. Missing, incompatible, incomplete, oversized, or changing indexes return
409 with a next step. Neither endpoint builds embeddings or calls a model.

Core reads only the currently selected provider/model namespace, checks vector
counts/dimensions and mapping order, and detects index file changes during the
read. Deleted documents are filtered through the catalog; stale embeddings are
excluded. This is a consistency check, not a cross-file transaction: if an
index is being rebuilt, wait for it to finish and refresh. A map and subsequent
related response may have different identities; the UI prompts a refresh.

Each document is represented by the normalized mean of its normalized chunk
vectors. Chunk count is disclosed; this aggregation can dilute a smaller topic
inside a long document. The map uses centered PCA via
[NumPy SVD](https://numpy.org/doc/stable/reference/generated/numpy.linalg.svd.html)
with stable axis signs, and handles empty, single-document, and identical-vector
spaces. The axes are not named topics or inferred categories. Overlapping
points remain selectable through the document list.

Neighbors are ranked using cosine similarity in the full document vector
space, not distance in the 2D picture. A low explained-variance percentage
means the map loses much of the original geometry. Scores can be negative;
they are not probabilities. Lexical hashing or unverified embeddings are
explicitly labeled and are not presented as semantic understanding.

The map displays at most 500 documents in stable file-ID order, with counts
and a subset notice. Related ranking uses all eligible scope members, including
documents outside that subset. For predictable memory use, this first version
limits a scope to 5,000 documents and 64 MiB of document-vector accumulators,
and accepts flat inner-product indexes up to 1,000,000 chunks, 8,192 dimensions,
1 GiB of vectors, and 512 MiB of mapping data. The
[FAISS flat index](https://faiss.ai/cpp_api/struct/structfaiss_1_1IndexFlat.html)
retains the vectors needed for reconstruction. There is no persistent
projection cache, automatic clustering, topic naming, or cross-model comparison.

## Verify and run

From the repository root, run Core's topic/scoping/index tests:

```bash
UV_PROJECT_ENVIRONMENT=./osii-env uv run --frozen --python 3.12 --package osii --extra dev python -m pytest osii-core/tests/test_topics.py osii-core/tests/test_scopes_api.py osii-core/tests/test_embedding_checkpoint.py
```

From `osii-dashboard/dashboard`, run `npm test` and `npm run build`. In a real
browser check selection, related-document navigation, scope changes, empty
filters, keyboard selection, and missing-index recovery links. Test a complete
index as well as the no-index state; never fabricate production embeddings
just to populate the view.

With `make dev` (Windows: `.\scripts\osii.ps1 dev`), Core reloads and Vite
updates automatically; refresh the browser after changes to the app registry.
For a production frontend, rebuild and serve the dashboard assets and restart
Core with the new routes. This work targets OSII-local on `main`; server
persistence/authentication and deployment are maintained separately.
