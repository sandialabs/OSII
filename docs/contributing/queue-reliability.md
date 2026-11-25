# Intake queue reliability

An intake run is a batch with a result for each file and each requested stage.
A failed source read should leave that file visible in Activity. A failed
summary or enrichment should independently leave the extracted text available
for browsing and search.

## Recovery available now

- **Retry reading** repeats failed source reads and extraction and reuses completed
  extraction where possible. For a synced file that cannot be read, first make
  it available offline or select an accessible local copy.
- **Build embeddings from saved text** recovers a run that stopped before
  indexing. It uses the file results and chunking settings already saved in
  that run. Inspect Activity for any files it could not read or summarize.
- **Retry embeddings** resumes a failed embedding stage with its saved chunk
  checkpoints. The published index stays available while a run is retried.
  Changing the embedding model calls for an explicit index rebuild.

## Local queue stages

The worker saves the source identity and text fingerprint before releasing work
that uses the text. An embedding thread can submit ready text while synthesis
or enrichment is active. It groups waiting files in bounded batches, uses the
existing index writer lock, and publishes checkpoints and index snapshots
through the existing embedding implementation. The SQLite job store keeps
embedding receipts separate from per-file processing receipts, so a progress
write from one stage cannot overwrite the other.

**Queue & activity** shows stage counts. Open a run for per-file status,
prior diagnostics, and retries for reading, summaries, enrichment, or embeddings.
A retry skips successful stages for the same saved text. If reading produces a
different text revision, its dependent stages run against that revision.

## Shared queue follow-through

1. Persist receipts for source verification, extraction, synthesis, enrichment,
   and embeddings. Key each by library, source revision, processor and
   configuration fingerprint. Reuse the existing processing job store, worker
   leases, idempotent commits, and vector checkpoints. Design the API and status
   model together for local SQLite and server PostgreSQL.
2. Carry these dependencies through hosted and packaged deployments. Extraction needs readable source
   bytes. Summary, enrichment, and embeddings need saved text. The embedding
   worker can start as soon as text is ready and should continue while an
   optional summary is delayed. Publish index snapshots atomically and avoid
   concurrent writers for the same library and model.
3. Classify failures before retrying. Retry transient file and network failures
   with bounded backoff. Surface inaccessible originals, invalid model
   configuration, and corrupt documents with a specific action. Resume only
   the unfinished stages after pause or crash. Record attempt history so a
   retry can preserve evidence from the first attempt.
4. Show the queue in Activity with counts for readable files, saved text,
   embedded files, and unresolved problems. Offer retry for the affected files
   or stage. Show what was skipped and why, and keep completed outputs
   available while the remaining work proceeds.

Validate with mixed-format batches, unavailable cloud files, empty model
responses, provider outages, and forced restarts during OCR and indexing.
Run these checks against installed Windows and macOS builds as well as the
shared local and server APIs.
