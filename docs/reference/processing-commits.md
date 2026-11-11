# Shared processing commits

[Optional local PostgreSQL](local-storage.md) uses these same commit ports for
the Workbench and worker, without hosted accounts. Optional claim-generation
fencing on `JobCheckpoint` prevents an old worker claim from committing under a
reused worker ID. Embedding identity can include a credential-free connection
fingerprint; endpoint/model-binding changes require an explicit index rebuild.

Core's `osii.domain.storage.commits` defines the commit boundary for completed
Processor API responses. It complements the [shared reads](library-reads.md).
Processor authors keep using the existing SDK: they return results, never a
storage path, database connection, or commit command.

## Contract

`ProcessingCommitter.commit(command, checkpoint=None)` accepts a
`ProcessingCommit` (a document step) or `ScopeProcessingCommit` (a scope product)
and returns a `CommitReceipt`. A document command supplies:

- A stable operation ID and document ID.
- The actual SDK request, response, and expected processor descriptor.
- For derived work, the input representation ID and full-text SHA-256 captured
  **before** calling a processor, not reconstructed from whichever text is current
  after it finishes.
- For extraction, explicit source metadata and optional already-computed chunks.
- Provenance and the extraction promotion policy. The text separator is explicit
  so adapting existing workflows does not silently change citation offsets.

Document commits cover extraction, synthesis, enrichment, and embedding.
Scope commits cover synthesis and enrichment over folders, collections, and the
root library using the same Processor API v1 requests and standard artifacts.
Hosted scope tools also use them for their existing object-scoped product views.
Extraction and embedding remain per-document operations, including when queued
over a folder or collection. No synthetic aggregate document is created.

Validation checks request/response identity, processor name/version/kind, explicit
scope, typed artifacts/citations, extraction source identity, chunk spans, ordered
embedding IDs, finite vectors, model choice, and claimed normalization. It occurs
before canonical publication. A stale input or an operation ID reused for a
different command raises `CommitConflict` rather than overwriting newer work.

The request's model-gateway context is excluded from fingerprints and saved
provenance. Provider API keys are not inputs to this storage interface. Source
text and intentionally supplied expert guidance remain library data; this is
not a content-redaction mechanism.

For example, Core orchestration around a synthesizer uses:

```python
from osii.domain.storage.commits import InputRevision, ProcessingCommit

revision = InputRevision.capture(reader, file_id)
response = processor.synthesize(request)
receipt = committer.commit(ProcessingCommit(
    operation_id=operation_id,  # Reuse this ID for the same job step on retry.
    file_id=file_id,
    request=request,
    response=response,
    expected_processor=descriptor,
    input_revision=revision,
))
```

`reader`, `committer`, `request`, and `descriptor` are supplied by the owning
composition. No application startup or model call is hidden inside a committer.
A completed receipt replays without creating another extraction or product.
Changing the command requires a new operation ID. Transient request IDs and
short-lived model tokens do not change the commit fingerprint.

## Folder, collection, and root products

`ScopeProcessingCommit` carries a `ReadScope`, a `ScopeInputRevision`, the SDK
request/response, expected processor, and provenance. Root uses
`ReadScope("root", "root")`. Local folder identifiers are existing logical folder
IDs; hosted folder identifiers are source-relative paths. Each composition
resolves its own membership; sources are never output directories.

`ScopeInputRevision.capture(reader, member_ids)` freezes complete sorted
membership and every available preferred-text representation ID and full-text
SHA-256 **before** dispatch. The composition freezes the actual request inputs
at the same time. Queued workflows serialize this revision alongside their
bounded text snapshots; they never recapture it after a model returns.

Requests may contain excerpts or a disclosed subset of members, but every
supplied document needs a frozen revision. Citation spans are checked against
the **supplied excerpt**, not the longer source. Citations to other documents
are rejected; multi-document character spans require a file ID.

Adapters re-resolve membership and compare preferred text before publication.
Added/removed members, changed extraction versions, edits, and changes outside
a retained excerpt reject the new commit. A matching completed receipt still
replays after later source changes without reactivating an old product. Scope
kind and ID namespace receipts, so identically named folders and collections
cannot collide. Scope receipts have `file_id=None` and explicit `scope_type` and
`scope_id`; existing document receipt fields remain compatible.

Optional `product_parents` freezes editorial heads by product filename. If a
head changed during a run, the result becomes a candidate rather than replacing
it. Without a parent map, the existing generated-product replacement policy
applies. Human revisions remain selected in either case.

## Sidecar adapter

`SidecarProcessingCommitter(root)` belongs to local Core. It uses the existing
extraction-version and product-history formats and serializes commit commands
with a cross-platform file lock. Completion receipts are atomic JSON records
under `.osii/runs/commit-<id>.json`; they are operational state, not a replacement
for document evidence, product histories, or inventory SQLite.

Extraction builds a complete immutable version before registering/promoting it.
The deterministic version ID and bundle commit marker make interrupted
registration/promotion retryable. Existing primary versions and downstream
staleness behavior are preserved. The legacy compatibility mirrors still have
their existing multi-file promotion behavior; this is not a filesystem-wide
transaction or a new guarantee for concurrent writers bypassing this boundary.

Each synthesis or enrichment product has an atomic history manifest. A
multi-artifact enrichment commits products individually: completed products can
be visible if a later product fails. The step receipt is written only after all
products finish. Retry repairs compatibility files and completes remaining
products without duplicating revisions. Human edits remain selected; regenerated
products remain candidates according to the existing authoring policy.

Aggregate products retain their existing synthesis/enrichment paths and generic
views. Verification reads canonical membership and object metadata, bypassing
the derived catalog. Multi-output steps remain resumable, not filesystem-wide
transactions. The commit lock coordinates commit-interface writers, not every
external editor or legacy writer; independent edits can make a result stale
immediately after verification.

Embedding commits persist a validated response and vector-space identity under
`.osii/embeddings/processor-results/`. They do **not** publish a serving FAISS
generation. The existing full and incremental index builders retain ownership
of checkpointing, vector reuse, and snapshot activation; they are not rewritten
or made to duplicate all their vectors through this interface in this slice.

Normal local Intake's staged extraction publication and remote synthesis and
enrichment (document, folder, collection, root) now use these commits. Legacy direct extraction
and in-process synthesis/enrichment entry points retain their existing behavior.
Local queue checkpoints remain in their existing operational database; passing
a hosted `JobCheckpoint` to the sidecar committer is rejected explicitly.

## PostgreSQL adapter

`PostgresProcessingCommitter(engine)` uses the existing hosted schema and optional
PostgreSQL dependencies. No schema migration, hosted login, or file fallback is
introduced into local startup. Results and commit receipts (namespaced records
in the existing settings table) are saved in one transaction. Per-document locks
serialize commits; an optional `JobCheckpoint` validates the worker's live lease
and saves the item checkpoint in that same transaction. A failed checkpoint or
expired lease rolls the result back too.

Hosted ingestion, per-document synthesis/enrichment, embedding-only jobs, and
scope-tool runs use the adapter. Existing HTTP envelopes, historical products, queue controls, and
legacy per-job artifact IDs remain compatible. Extraction replaces current
chunks only when the version becomes primary. Synthesis/enrichment retain the
input extraction identity and digest, so re-extraction makes old outputs stale.

Scope results use the existing `scope_products` and `scope_revisions` tables,
filenames, revision history, and human-edit protections; no migration is added.
A serializable transaction checks membership and full input revisions, writes
all products and the receipt, and checkpoints the job. Concurrent writes can
require retrying the transaction. Failed transactions expose no partial products.
Authorization remains at the hosted API/worker boundary; private collection
visibility is rechecked using the supplied actor context. No sidecar fallback
is introduced.

Embedding-only commits require the complete current document chunk set. They
record model/provider/dimensions/normalization provenance and reject conflicting
known vector-space identities for the same model. Existing vectors that predate
identity tracking do not gain verified provider identity retroactively; a full
generation migration is separate work. This does not implement a new vector
database, index generation policy, or automatic provider fallback.

## Verification and next work

Run the [read-contract PostgreSQL setup](library-reads.md#verify-parity), then add
`osii-core/tests/test_processing_commits.py` to the same pytest command. Tests
exercise both adapters with a real isolated PostgreSQL schema, including stale
inputs, reused IDs, variants, citations/geometry, multi-product retry, vector
validation, token exclusion, lease checks, and transactional checkpoint failure.
Scope cases cover all three aggregate scopes, bounded excerpt citations,
membership and full-text changes, human revisions, and unchanged local HTTP
adapters. Hosted workflow tests cover the migrated scope-product schema and
pause/resume behavior.
The hosted suite separately tests the migrated schema and existing workflows.
Sidecar product-history cases run in the local checkout; the hosted checkout
does not acquire the local authoring implementation just to run those cases.

These low-level commits do not choose a backend. The
[local Workbench composition](local-storage.md) now provides explicit selection
and library import. Broader legacy adoption and inventory migration remain
separate work. See the
[storage decision and staged plan](../concepts/adr-storage-boundaries.md).
