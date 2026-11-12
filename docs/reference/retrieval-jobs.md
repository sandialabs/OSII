# Shared retrieval and job interfaces

Core now has two additional small boundaries alongside [reads](library-reads.md),
[processing commits](processing-commits.md), and [authoring](library-authoring.md).
They preserve the existing local and hosted compositions rather than introduce a
universal database, queue broker, search engine, or startup mode.

## Bounded retrieval

`osii.domain.storage.retrieval` defines `Retriever.retrieve(RetrievalRequest)`.
A request carries the query, `ReadScope`, lexical/semantic/hybrid mode, result
limit (1–50), and a text budget (default 64,000 characters). Optional file grouping
uses the existing local search behavior.

`RetrievalResult` contains typed hits, actual retrieval mode, reported channels,
an optional corpus revision, and a `limited` flag. Hits retain document and passage
IDs, representation identity when supplied, source paths, exact source offsets,
geometry/provenance, score, snippet, and full passage text when the backend supplies
it. A snippet is explicitly a display excerpt: its length need not equal the
source span. No missing representation or corpus revision is fabricated.

```python
from osii.domain.read.contracts import ReadScope
from osii.domain.storage.retrieval import RetrievalRequest

result = retriever.retrieve(RetrievalRequest(
    "detector calibration", ReadScope("collection", collection_id),
    mode="hybrid", top_k=6,
))
for hit in result.hits:
    print(hit.file_id, hit.passage_id, hit.char_start, hit.snippet)
```

`BoundedRetriever` adapts a composition-supplied native search function. It checks
identifiers, spans, finite scores, count, and aggregate text/snippet size; removes
embedding vectors from returned rows; and keeps backend metadata. Oversized hits
are omitted, not truncated while pretending their offsets changed. `limited`
reports this. Scores and ranking are backend-specific and not comparable across
indexes. Empty channels mean the native adapter did not report channels.

Local POST Search uses `retrieve_dashboard` around existing BM25/FAISS retrieval.
Hosted `Library.search` delegates through `Library.retrieve`, retaining its
authorized scope selection and native ranking. Existing HTTP envelopes and
ordinary result fields remain compatible. Native lexical/hybrid fallback and
strict semantic-mode failures remain native policies. Missing local folders now
match nothing rather than accidentally searching the root.

Scope authorization is the native composition's responsibility, **not** a claim
that any supplied callback becomes safe merely by wrapping it. Local folder IDs
and hosted source-relative folder paths retain their established meanings.
Advanced RAG profiles keep their existing evidence hydration, corpus guards,
reranking, trace, and model-call limits; this does not rewrite those workflows.

These are bounded **request/result** interfaces. They do not make hosted ranking
database-paginated: the existing `Library.scoped` snapshot still materializes its
corpus before ranking. Eliminating that whole-corpus read and benchmarking large
collections remain separate work. Existing index formats and publication remain
unchanged; no vector-space migration or automatic embedding-provider switch occurs.

## Explicit job ownership

`osii.domain.storage.job_store.JobStore` defines submit, get, bounded list (1–100),
claim, heartbeat, checkpoint, finish, and pause/resume/cancel/retry controls.
`JobRecord` keeps the queue job ID separate from its run ID. Local queues have
both IDs; hosted jobs use the same ID for both. Native envelopes remain available
for compatibility, not a new public REST schema.

```python
claimed = jobs.claim(worker_id)
if claimed is not None:
    jobs.heartbeat(claimed.lease)
    # Execute an already validated, bounded Core workflow here.
    jobs.checkpoint(claimed.lease, index=0, item={"status": "done"})
    jobs.finish(claimed.lease)
```

Every mutation by a worker requires its `JobLease`: job ID, worker ID, and a
unique claim generation. Expired, released, wrong-owner, and superseded claims
raise `JobOwnershipLost`. A late heartbeat cannot resurrect an expired claim;
a late completion cannot overwrite a reclaimed run, even when worker IDs repeat.
The generation is operational fencing metadata in the existing job payload,
not a provider secret or a user-authentication token.

Pause/cancel remain cooperative: a current operation can finish, then a checkpoint
or completion acknowledges the control. Completed items remain saved on resume
or retry. PostgreSQL raw `pausing`/`cancelling` map to shared
`pause_requested`/`cancel_requested`; native API states are unchanged.
Normal batch rescheduling releases the claim without consuming PostgreSQL's
three-attempt worker-recovery budget.

`SidecarJobStore(root)` owns only existing `.osii/state/jobs.sqlite3`, never the
canonical volume inventory. Its explicit context does not switch the process's
default library. Local legacy helpers remain compatible. `PostgresJobStore(engine)`
uses the existing hosted jobs table and transactions, without a schema migration,
file fallback, or hosted startup in local Core. The API/launcher still supplies
validated payloads; hosted authorization and model-configuration checks remain at
their existing boundaries. Low-level job access is not a permission grant.

Both normal worker loops now use shared claims, heartbeats, and fenced completion.
Existing processors, output commit adapters, job activity views, aliases, and
controls keep working. PostgreSQL keeps its single-writer advisory lock and
five-minute lease; local recovery keeps its fifteen-second heartbeat policy.
Native retry details, configuration validation, operational payloads, and recovery
limits are not made artificially identical. Legacy writers bypassing the new
interface are not covered by its generation checks.

Checkpoints do not make source-processing and queue updates one distributed
transaction. PostgreSQL processing commits retain their existing atomic
output/receipt/checkpoint boundary; sidecars retain resumable file publication
and separate operational state. Fair scheduling, resource-aware concurrency,
priority, and full adoption of shared step checkpoints remain later work.

## Verification and startup

Use the [isolated PostgreSQL test setup](library-reads.md#verify-parity), adding
`osii-core/tests/test_retrieval_jobs.py` to the shared contract test command.
Cases exercise scope/source metadata through both read adapters, bounded results,
expiry and reclaim, stale-worker rejection, controls, retries, progress retention,
and independent local stores. Retrieval contract fixtures deliberately control
ranking; existing local and hosted search suites verify actual native ranking,
provider fallback, permission checks, and citations. Worker-loop tests exercise
real queue adapters with fake processing, without contacting models.

Startup remains `make dev` or `.\scripts\osii.ps1 dev` on local. Optional local
PostgreSQL now composes these same job ports; see [local storage](local-storage.md)
for explicit selection and import. Its bounded file/model steps release claims
between units and keep optional Intake work under the parent run's controls.
Private embedding checkpoints are not public Activity payloads. Hosted startup,
authentication and migrations stay separate; no broker or model download is added.
