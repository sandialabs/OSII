# Shared processing commits

Core's `osii.domain.storage.commits` defines the commit boundary for completed
Processor API responses. It complements the [shared reads](library-reads.md).
Processor authors keep using the existing SDK: they return results, never a
storage path, database connection, or commit command.

## Contract

`ProcessingCommitter.commit(command, checkpoint=None)` accepts a
`ProcessingCommit` and returns a `CommitReceipt`. The command supplies:

- A stable operation ID and document ID.
- The actual SDK request, response, and expected processor descriptor.
- For derived work, the input representation ID and full-text SHA-256 captured
  **before** calling a processor, not reconstructed from whichever text is current
  after it finishes.
- For extraction, explicit source metadata and optional already-computed chunks.
- Provenance and the extraction promotion policy. The text separator is explicit
  so adapting existing workflows does not silently change citation offsets.

The initial boundary commits one document's extraction, synthesis, enrichment,
or embedding result. Existing aggregate folder/collection/root workflows remain
available through their current adapters; this does not add hosted aggregate
processing or migrate it into the new boundary.

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

Embedding commits persist a validated response and vector-space identity under
`.osii/embeddings/processor-results/`. They do **not** publish a serving FAISS
generation. The existing full and incremental index builders retain ownership
of checkpointing, vector reuse, and snapshot activation; they are not rewritten
or made to duplicate all their vectors through this interface in this slice.

Normal local Intake's staged extraction publication, remote document synthesis,
and remote document enrichment now use these commits. Legacy direct extraction
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

Hosted ingestion, per-document synthesis/enrichment, and embedding-only jobs use
the adapter. Existing HTTP envelopes, historical products, queue controls, and
legacy per-job artifact IDs remain compatible. Extraction replaces current
chunks only when the version becomes primary. Synthesis/enrichment retain the
input extraction identity and digest, so re-extraction makes old outputs stale.

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
The hosted suite separately tests the migrated schema and existing workflows.
Sidecar product-history cases run in the local checkout; the hosted checkout
does not acquire the local authoring implementation just to run those cases.

This boundary does not make `.env` backend selection available. Remaining work
includes broader adapter adoption, aggregate commits, shared job interfaces,
complete authoring parity, and explicit inventory/library migrations. See the
[storage decision and staged plan](../concepts/adr-storage-boundaries.md).
