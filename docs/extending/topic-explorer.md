# Topic Explorer view extension contract

Topic Explorer has three boundaries: **Core data**, a **shared interaction panel**,
and a **registered visualization**. Local and server share the latter two; their
HTTP, persistence and authorization adapters remain separate. Registration is
reviewed source code compiled with the application. It is not a runtime loader
for arbitrary JavaScript or an installation mechanism for model services.

## Register a visualization

1. Add a component under `osii-dashboard/dashboard/src/features/topics/`.
2. Implement `TopicViewProps` from `components/viewTypes.ts`.
3. Import it and add one `{ id, label, View }` entry to `components/views.ts`.
   IDs must be unique and stable. The shared panel displays a view picker when
   more than one view is registered. No product page or sidebar edit is needed
   for another visualization inside Topic Explorer.
4. Keep the registration and view shared between branches. The product pages
   supply HTTP and collection adapters; do not import PostgreSQL, sidecars,
   filesystem access or model credentials into the visualization.

```tsx
import type { TopicViewProps } from "./components/viewTypes";
export function MyView({ points, selectedIds, onSelect, onSelection }: TopicViewProps) {
  // Render points and provide keyboard-accessible focus and selection controls.
  // onSelect(fileId) focuses a document; it does not add it to a collection.
  // onSelection?.([fileId], "add") proposes collection membership for review.
  return null;
}
```

| Prop | Contract |
| --- | --- |
| `points` | Mapped documents: stable `file_id`, source identity, optional derived metadata, chunk count, finite `x/y` coordinates. Do not mutate inputs. |
| `selectedId` / `onSelect(id)` | Focus one document for inspection. |
| `relatedIds` | Similar documents ranked by Core in the full embedding space. |
| `selectedIds` | Controlled collection selection; retain source IDs. |
| `onSelection(ids, mode)` | Propose `replace`, `add`, or `remove`. The panel rejects IDs outside the current map. Never write collections directly from a view. |
| `resetPreviewToken` | Changes clear temporary preview gestures after save/dismiss while keeping the camera position. |
| `onPreview(ids)` | Preview a possible group without saving membership. The panel supplies thumbnails, checkboxes and an explicit save action. |

`TopicExplorerPanel.tsx` owns bounded search results, selection review, creation
and addition through supplied collection callbacks, and advanced metadata rendering.
A view error boundary preserves those controls if a visualization fails.
`geometry.ts` owns aspect-preserving pan/zoom positions and circle hit testing;
`presentation.ts` owns label, hover and search semantics. Reuse them where suitable.

The built-in map supports pan, circle selection and nearby preview. Shift adds
and Alt removes when drawing; Escape cancels. Search and review checkboxes provide
keyboard alternatives. Nearby groups are geometric suggestions, not validated
named topics. Inspect documents before saving a collection. Scope/index changes
reset the selection; changing label or preview settings does not change geometry.

## Core data and scope limits

Both products expose `POST /api/topics/map` and `/api/topics/related`.
The default map includes **every document with current, compatible embeddings**
in the authorized scope; there is no 500-point or 5,000-document scope cap.
Search and graphical selection use that full set. The local API's optional
`limit` restricts returned points only; fitting still uses the entire scope.
Stale and unindexed files remain counted separately. Search shows at most 50
suggestions after two characters; collection review initially mounts 24 cards.
Related ranking uses the original document vectors, not the 2D projection.
Neither route calls a model.

Shared `topic_projection.py` uses exact PCA for small spaces and fixed-seed,
oversampled approximate PCA for larger spaces. All documents participate in the
fit, with linear workspace and a small subspace decomposition rather than a full
corpus SVD. Cached geometry is derived and rebuildable, not topic assignments.
The versioned cache invalidates old subset maps. Document vectors are float32
with a 64 MiB matrix budget (about 10,922 documents at 1,536 dimensions or 43,690
at 384 dimensions). This memory guard returns an actionable error rather than
silently sampling. Local FAISS index/mapping size guards still apply.

The shared renderer paints all points on a canvas and mounts only viewport,
screen-density representatives for thumbnail/label detail. Zoom (up to 64x) and
pan change the representatives; this is rendering detail, never dataset sampling.
Hit testing, search and circles operate on every point, including overlapping
points with no individual thumbnail. Circle/nearby review exposes individual
files before saving a collection. Custom views must preserve this separation
and avoid mounting a React component or thumbnail job per dataset entry.

A new algorithm is a Core/processor capability change, not merely a different
renderer. Preserve index identity, scope membership, model provenance and
invalidation. Use the four Processor SDK kinds for new computation methods;
local's workbench catalog already distinguishes topic modeling, projection and
recommendation operations. A whole new workspace uses the product's routing and
navigation adapter; the local general specification is `frontend-tools.md`.

## Thumbnails and advanced metadata

PDF preview detail is chosen by viewport and screen density, with no ID-order
cutoff. Representatives automatically use the existing cached browser renderer
and its two-job concurrency queue. Off-screen previews are deferred; failures retain a file marker and an explanation. Review
cards paginate at 24 to avoid mounting thousands of preview renderers. Advanced
map controls adjust thumbnail size, nearby radius, label visibility and the
metadata field used as the label. These controls do not rewrite any document.

Advanced document metadata reuses local's `SuggestedMetadata` field editor. It
supports descriptive title, printed title, author, date, agency and document type.
Blank and qualitative values are permitted. `GET/PUT /api/objects/{id}/metadata`
use `expected_revision` (null for the first human edit). A conflict returns 409;
the draft is preserved and the user must review the latest revision. Original
files and generated suggestions are retained separately. Human corrections take
precedence in map labels and survive re-extraction and later AI synthesis.

Local persists edits through its existing product revision service. Server stores
current corrections and prior revisions in PostgreSQL artifacts and audits writes;
only curators/admins may save shared corrections. All authenticated users may read
them and create private collections; existing publication rules remain unchanged.
A custom editor must use the product's transport adapter (including hosted CSRF)
and must not bypass Core permission or revision checks.

## Verification

Run frontend tests and builds on both branches. Browser-test more than 40 PDFs,
zoomed/panned circle selection, nearby preview, search without a giant option
list, keyboard review, collection creation/addition and failed saves. Test metadata
reader/curator permissions, stale revision conflicts, regeneration after a human
edit and preservation of original filenames/text. New views must handle empty,
partial and stale data, avoid model calls during viewing, and provide accessible
controls. See local's `frontend-tools.md` for the broader workbench contract.
