# ADR: Incremental selected-document embeddings

Status: accepted 9 November 2026.

## Context

Intake previously invoked a whole-library vector rebuild after processing its
files. Adding a bounded batch could resend unrelated documents to the embedder
and replace existing vectors. Its ordinal checkpoint could skip a failed middle
chunk after later chunks succeeded, and indexing failures left the run done.
The existing portable document sidecars and model/provider index namespaces must
remain usable, including indexes created before this change.

## Decision

Intake and selected Library processing call `embed_selected_documents` with the
successful document identities from that run, deduplicated by content identity.
They read only those documents' preferred extracted/edited text. Originals are
never read by the embedding phase. A saved file-phase completion marker and
frozen embedding document IDs keep retries and worker recovery from repeating
extraction, summaries, or enrichment. A failed embedder leaves the run in error;
**Retry embeddings** in Activity continues the same document set. Pause/cancel
is cooperative between requests, with checkpoints retained.

Each provider/model namespace has a derived `incremental.sqlite3` cache on local
disk. Successful provider responses commit vector blobs and mapping metadata
transactionally before progress is reported. Keys include the full chunk-text
hash, extraction/representation identity, spans, chunk settings, and input
truncation policy. Retry finds missing keys rather than advancing past a highest
completed ordinal. Healthy documents continue after an individual failure;
successful chunks within an incomplete document also survive restart. Publishing
rechecks the selected text revision. Only complete current documents replace
that document's old vector rows; other documents remain unchanged.

The cache pins provider, requested model, endpoint fingerprint, and processor
version. Dimensions and model digest (when supplied) are checked too. A changed
connection cannot silently reuse or mix vector spaces; restore the original
connection to retry, or deliberately start a separate provider/model index.
API credentials are not stored in this identity. Providers that silently change
a model behind the same identifier without reporting a digest cannot be detected
fully by the client; use stable versioned model identifiers.

Index publication writes a new immutable directory containing FAISS vectors,
mapping JSONL, and metadata TOML, then atomically replaces `current.json` after
flushing the files. Readers pin one directory for the entire read. Interrupted
publication leaves the prior snapshot usable; retry uses cached vectors without
another provider request. An OS advisory writer lock spans the library, including
explicit full rebuilds, and releases on process exit. The keyword chunk manifest
merges completed selected documents while retaining other saved chunks. Catalog
index records refresh without scanning unrelated document sidecars.

Existing flat indexes remain readable. The first incremental update preserves
unselected legacy vectors exactly. Fingerprinted vectors from a newer full build
can seed the cache; older rows without fingerprints are regenerated only if that
document is selected. No source, sidecar library, canonical inventory, or legacy
index is implicitly deleted or migrated.

The standalone `python -m osii.build_vector_index --osii-root PATH` command is
still an explicit full-library rebuild. A successful full rebuild supersedes the
old incremental cache; its fingerprinted output seeds later selected updates.
It is not invoked by Intake. Provider readiness checks remain separate small
connection probes, rather than corpus backfills.

## Consequences and recovery

Completed chunk requests are not repeated after durable commit. A worker exit
or lost response before commit can still repeat a provider request; exactly-once
billing is not promised. Recover queued worker jobs normally or use Activity to
retry. No inventory schema migration is required.

FAISS publication still reads/copies the existing index locally and retains old
snapshots, so disk use and publication time grow with the index. Model input and
chunk generation are bounded by the selected documents. Old snapshots and cache
rows are retained for recovery; there is no automatic retention cleanup. Keep
runtime databases and snapshots on local disk, separate from SMB/NFS originals.

Failures in publication or local disk writes preserve committed cache entries.
Restore storage availability and retry. Corrupt/incompatible cache or index data
fails clearly; restore a matching backup or deliberately perform a full rebuild
rather than silently discarding completed work. The cache and vector indexes
remain derived from canonical document sidecars and can be rebuilt explicitly.
