# Shared authoring and collections

`osii.domain.storage.text_authoring` adds a shared `get/save` preferred-text port
with an expected revision, immutable extraction evidence and retained human
history. PostgreSQL edits regenerate lexical chunks from the selected saved text
and invalidate vectors; the pure `chunk_saved_text` helper performs no source IO
or model calls. This port is composition-supplied, not a new hosted permission
grant or public editing route. Local and PostgreSQL contract tests cover it.

Core's `osii.domain.storage.authoring` defines two small interfaces:

- `ProductAuthoring`: read history, save a draft, and activate a revision.
- `CollectionStore`: list/get collections, create one, update its name or
  description, and replace its membership with a stale-write check.

They complement [shared reads](library-reads.md) and
[processing commits](processing-commits.md). Processors still return SDK output;
they do not edit the store. These interfaces do not select a backend, run models,
introduce authentication, or migrate a user's library.

## Saving and activating a product

`ProductRef` identifies a scope, an existing product filename, and its family
(`enrichment` or `synthesis`). Use logical local folder IDs or hosted
source-relative folder paths, as in the processing interfaces. Root uses
`ReadScope("root", "root")`. Filenames are backend locators, not portable IDs:
obtain them from the owning product list instead of translating a sidecar path
into a hosted filename.

```python
history = authoring.history(product)
draft = authoring.save(
    product,
    {**history.active.data, "markdown": "Human-reviewed description."},
    expected_revision=history.active_revision,
)
# The previously active product is still selected. Review the draft first.
chosen = authoring.activate(
    product, draft.revision_id, expected_revision=history.active_revision,
)
```

The composition supplies `authoring` and `product`. Saving returns a
`ProductRevision`; history is a `ProductHistory` with an active revision and all
earlier revisions. Revisions retain their data, input provenance, citations,
parent, and available attribution. Human changes are marked as needing grounding
review; old OCR geometry is not invented for new prose.

Activation appends a new human editorial event containing the chosen content.
It does not delete or rewrite the chosen revision. Generated processing results
remain candidates while a human revision is active. Both save and activation
check `expected_revision` and raise `AuthoringConflict` (a `FileExistsError`) if
the active revision changed. Multiple drafts may branch from the same active
revision; activation still requires a fresh active-revision check.

`save(..., activate=True)` is an explicit compatibility operation. Existing
Workbench product editors use it to retain their one-button save behavior.
They have **not** silently become a draft-only UI. Legacy product editing and
restore helpers now delegate to the shared adapters. Existing REST envelopes,
filenames, product histories, and editor controls remain compatible.

Edits preserve the product format. Standard tables, entity lists, graphs, and
wiki Markdown are schema-validated; this reuses existing editing capabilities,
not a new specialized editor. Existing document-metadata edits retain the human
method marker. Citation field shapes are not expanded just by saving. Existing
size limits remain: 5,000,000 serialized JSON characters for local products and
4,000,000 for hosted products; keep portable edits within the smaller limit.

## Storage guarantees

`SidecarProductAuthoring(root)` uses existing `.history` manifests. Legacy JSON,
text, and Markdown remain readable without a migration on lookup. On first edit,
the prior payload is retained as an imported revision. A draft commits history
only: it does not reformat or replace the active compatibility file. Activation
commits the history manifest before refreshing that file. Manifest-aware readers
remain authoritative if refreshing a compatibility file is interrupted.

`PostgresProductAuthoring(engine, actor_id=...)` uses existing `scope_products`
and `scope_revisions` tables. Revision insertion and activation are transactional;
row locks protect stale-write checks. No schema migration or sidecar fallback is
introduced. Hosted routes still enforce role, collection visibility, and input
reference checks before calling the adapter. Actor IDs supplied to Core are
attribution/filtering context, not authentication credentials or permission grants.

Both adapters preserve source text, extraction versions, and existing generated
outputs. A product edit does not automatically rebuild search, invoke a model,
or change the preferred document representation.

## Collection commands

`SidecarCollectionStore(root)` reads canonical `collection.toml` and membership
files rather than trusting the derived catalog. `PostgresCollectionStore(engine,
actor_id=..., visibility=...)` uses existing collection rows and filters private
records by the supplied owner context. Hosted authorization remains outside the
interface, including permission to change a shared collection.

```python
collection = collections.get(collection_id)
renamed = collections.update(
    collection_id, name="Reviewed experiments", expected_version=collection.version,
)
updated = collections.replace_members(
    collection_id, selected_file_ids, expected_version=renamed.version,
)
```

The version is an opaque token over current metadata and membership. A metadata
change invalidates an old membership token, and vice versa. Duplicate member IDs
are normalized. Commands never delete original files or document artifacts.
Membership changes make earlier scope-processing inputs stale without deleting
authored products. The caller decides which document IDs are valid for its
workflow; the hosted REST API retains its existing document/visibility checks.

Local commands retain unknown collection fields, colors, timestamps, and retained
member annotations. Hosted commands preserve ownership and visibility. Each
local command changes one canonical file atomically, then refreshes the derived
catalog; a catalog failure cannot roll back a completed canonical write. Metadata
and membership are deliberately separate commands, not a claimed multi-file
transaction. PostgreSQL performs each command in a transaction. Creation and
name uniqueness retain backend-specific rules; these are not account-management
or universal collection-identity operations.

Collection adapters are available to Core/Python callers. Legacy collection REST
handlers remain compatible; their authorization and envelope convergence is
incremental, not a new replacement API. Writers bypassing the interfaces and
independent filesystem editors are not covered by their locks. Shared deletion,
collection revision journals, and collection transfer are not implemented here.

## Deliberate remaining boundaries

Legacy `edited_text.json` segment overrides, whole-document text correction,
and extraction promotion remain unchanged. They are **not** silently imported
into product histories or claimed as shared document-text authoring. Unifying
those operations requires explicit representation identities, grounding, stale
index behavior, and a verified migration preserving existing overrides. Research
report revisions likewise retain their separate authoring workflow.

## Verification

Run the [isolated PostgreSQL setup](library-reads.md#verify-parity), then include
`osii-core/tests/test_library_authoring.py` with the shared read/commit tests.
The same cases exercise draft/activation, conflicts, original revision retention,
failed publication, typed products, collection versions, annotations, private
collection filtering, and scope invalidation. Hosted workflow tests separately
check the existing editors and permissions against migrated tables. Tests use
temporary sidecars and databases, never a user's documents or inventory.
