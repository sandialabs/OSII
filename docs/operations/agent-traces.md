# Demonstrate advanced RAG and inspect an agent trace

OSII-server's Chat page offers experimental query-time strategies over the
existing PostgreSQL dataset. Strategy selection does not ingest, reorganize,
or re-embed documents. Original sources stay read-only. The design is grounded
in the [agent trace literature review](../concepts/agent-traces-research.md).

## Start a demonstration

1. Start the server with `make dev`, or use a deployment built from the updated
   server branch. Normal startup and the server requirements include the pinned
   Haystack dependency. No new database migration is needed for this feature.
2. Sign in and choose the document scope in **Chat**. A private collection remains
   restricted to its owner; model-generated queries cannot broaden that scope.
3. Select a RAG strategy and ask a question. Use **Coarse full-text + iterative**
   to demonstrate document filtering before passage ranking. Iterative strategies
   require a selected chat model in administrator Model settings.
4. Expand **Inspect agent trace** beneath the answer. Select a timeline stage to
   inspect its inputs, outputs, evidence, limits, exclusions, and timing.
5. Open **Evidence lineage** to follow a source through the stages. Use **Open
   source** to inspect the underlying document and recorded geometry.
6. Download the trace JSON to retain the run. Traces are returned with the answer;
   this first version does not maintain server-side trace history or share links.

Administrators receive detailed payloads. Other authenticated users receive
execution summaries with payloads removed by Core, rather than merely hidden
by the UI. Conversations remain in component memory, not shared browser storage.
Signing out, refreshing, changing scope, or starting a new conversation clears
the displayed conversation. Downloaded traces contain document content, queries,
history supplied to the model, and model output; handle them accordingly.

## Strategies and bounds

| Strategy | Behavior |
| --- | --- |
| Configured chat | Previous single-pass API behavior; no advanced trace |
| Keyword baseline | BM25 and OCR-tolerant retrieval, then a grounded decision |
| Hybrid baseline | Lexical/OCR and compatible vector results, then a grounded decision |
| Hybrid + reranker | Retrieve up to 40 candidates and rerank to at most 8; requires a configured Core reranker |
| Iterative hybrid | Up to 3 retrievals and 3 model decisions, accumulating evidence in the same scope |
| Coarse full-text + iterative | Normalized token-OR document search before passage retrieval on each iteration; up to 3 rounds |

Coarse search removes common question words and matches any remaining normalized
term in the extracted document text. It reports an exact matching-document count.
More than 500 matching documents stops that run with a request to refine the
question or scope, rather than silently choosing an arbitrary subset. This is
an explicit experimental filter, not SQL Boolean syntax, exhaustive semantic
search, or a guarantee of improved recall. A hard lexical filter can lose
relevant documents; compare it with the ordinary hybrid strategy.

The runner retains at most 24 passages and 24,000 evidence-text characters.
Candidate reranking is bounded to 64,000 text characters. A 90-second cooperative
deadline is checked between stages; it cannot interrupt an in-flight model
request. Model adapters have their own HTTP timeouts. Reranking is optional and
belongs in Core RAG, not Toolbox.

Advanced chat decisions request structured JSON using a JSON Schema and still
validate actions, budgets, and citation identities in Core. The selected endpoint
must support that protocol. OpenRouter requests require parameter support so it
does not silently discard the schema. Unsupported schemas or model failures are
visible failures; there is no retry of chat or switch to another model. See
[OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs)
and [model endpoint configuration](model-endpoints.md).

When no chat model is selected, keyword/hybrid baselines can return explicitly
labeled extractive excerpts; iterative planning is unavailable. Query-embedding
failures can use the existing keyword/OCR fallback, with the failure and fallback
shown in the trace. Compatible embedding model identity is required; matching
vector dimensions alone is insufficient.

## Read the trace accurately

The execution tree includes document search, query embedding, BM25, OCR-tolerant
search, semantic search, rank fusion, passage selection, optional reranking,
context assembly, model calls, and decisions as applicable. Stages that did not
execute are not invented. An iterative strategy can finish after one search
when the initial evidence is sufficient.

Candidate tables preserve source identity, available extraction identity,
character spans, and geometry. They distinguish exclusions caused by overlapping
passages, count limits, character budgets, and coarse filtering. Raw scores have
stage-specific meanings; they are not calibrated probabilities.

Each stage retains at most 200 returned and 200 excluded records. Passage previews
are limited to 4,000 characters, with explicit truncation and original-length
metadata. Recorded/omitted counts are shown independently of output counts.
Detailed generation inputs include the actual prompt and context sent to the
model, allowing inspection beyond the table preview. Credentials and provider
headers are never included in those inputs.

The trace is an execution record, not an answer-quality certificate. A stop
reason of `answered` records the controller's action; it does not prove that
each claim is entailed by its citations. Live runs show quality as unmeasured.
Chat usage is retained when reported by the provider. Query-embedding and custom
reranker tokens/cost are not included in that chat accounting.

Runs use one materialized PostgreSQL corpus snapshot, normalized scope, history,
and captured model configuration. Comparisons execute two or three strategies
sequentially against the same session. Current corpus revision, collection
membership/visibility, and model configuration are checked during execution.
A change aborts with HTTP 409 instead of returning a mixed comparison. A database
transaction is not held open during model calls.

## Compare strategies and evaluate quality

Enter a question, select two or three comparison chips, and click **Compare
selected strategies**. Each strategy makes its own calls and incurs normal
provider charges. The existing per-user/global budgets remain enforced, and
each actual advanced chat/embedding/reranking call counts toward its budget.
Failures retain their trace and error status; a successful comparison entry
does not conceal a failed entry.

The example API admits one advanced run per process, including a whole comparison,
to avoid loading multiple corpus/vector snapshots into its 1 GiB memory limit.
Overlapping advanced requests receive HTTP 429 and can be retried after the
active run finishes. This is admission control, not a background job queue.
Nested span durations include child work; do not sum every row as if it were
independent time.

For labeled questions over an existing dataset, use the read-only evaluator:

```bash
uv run --env-file .env --package osii --extra server --extra rag-haystack \
  python -m osii.server.evaluate questions.jsonl \
  --profiles lexical-v1 iterative-v1 coarse-iterative-v1 \
  --username heidikmkv --allow-model-calls --output /tmp/osii-rag-results.json
```

The CLI uses the configured PostgreSQL connection and an existing active
administrator principal. `--allow-model-calls` explicitly permits the selected
chat, query-embedding, and configured reranking requests. It does not change
models or bypass rate budgets. Adapt the output path on Windows.

Each JSONL row supplies `id`, `query`, `expected_sources` (relative source paths),
and optionally `scope`, `category`, `answer_contains`, and `unanswerable`.
`answer_contains` is a list of alternative groups: each group needs at least one
case-insensitive literal match. The report separates context-source recall,
citation-source recall, literal checks, and typed abstention. Recall is against
the labeled source set only. Literal checks cannot establish entailment, correct
units, or absence of additional false claims. Review answers and citations.

## Public pilot results, November 10, 2026

The checked-in fixture `osii-core/server-tests/fixtures/rag-nasa.json` contains
seven short, manually curated NASA-derived fact summaries with original source
URLs and six labeled questions: two single-source, three requiring multiple
sources or a bridge, and one unanswerable question. The corpus was loaded into
an isolated PostgreSQL test database, leaving the hosted dataset and model
configuration unchanged.

The final live run used the explicitly selected `openai/gpt-4.1-mini` chat model
and `openai/text-embedding-3-small` query/document embeddings, with temperature 0
and structured JSON decisions. It compared three strategies:

| Strategy | Answerable cases with all labeled sources in context | Cases with all labeled sources cited | Literal checks | Typed abstention on the unsupported question |
| --- | --- | --- | --- | --- |
| Keyword baseline | 5/5 | 5/5 | 5/5 | 1/1 |
| Iterative hybrid | 5/5 | 5/5 | 5/5 | 1/1 |
| Coarse full-text + iterative | 5/5 | 5/5 | 5/5 | 1/1 |

The final 18 runs used 18 chat calls and 13 embedding requests, including the
batch that embedded the seven document passages. Reported chat cost was
USD 0.015642; embedding cost was not captured by this adapter. The bridge question
correctly linked Uranus's tilt/backward rotation to Venus's 243-Earth-day rotation.
The unsupported mission-date question produced abstention without citations.

Earlier exploratory runs found an unsupported numerical comparison that literal
checks missed and responses describing missing information while declaring an
`answer` action. Prompt clarification and requesting supported structured JSON
decisions corrected those cases in the retest and final run. An initial SSH-based
provider bridge also had connection failures; those were not counted as evidence
of answer quality. Subsequent live calls used the already configured local model
connection directly, without copying credentials into fixtures or reports.

These questions were reviewed during development, so this is a pilot and regression
set, not a held-out benchmark. All needed evidence fit in the first retrieval;
these live results do not demonstrate a quality gain from iterative search or
coarse filtering. A separate controlled PostgreSQL/API regression demonstrates
a genuine second retrieval adding missing evidence. Additional tests cover
private scopes, administrator/reader trace separation, errors, corpus changes,
reranking provenance, context budgets, and unchanged source/index data.

The pilot does not validate OCR quality, large-corpus latency, reranker quality,
or retrieval over all hosted government documents. That deployment has a larger
corpus; its representative questions and supporting spans still need labeling.
Before changing defaults, add a held-out set from those documents and compare
source coverage, grounded claims, appropriate abstention, latency, and cost.

A subsequent deployment smoke test on November 10 used the existing hosted
corpus snapshot: 245 documents and 18,256 passages, revision 490. The question
“What does Lindgren put in an empty cat food can to trap slugs?” correctly
returned **stale beer**, citing the inspected government-document passage.
The coarse/iterative run produced 13 trace stages without retrieval warnings.
In a fresh release container with the API's 1 GiB memory limit, peak process
resident memory was about 461 MiB and elapsed time including corpus loading
was 42.6 seconds. This one cold-run check establishes deployment feasibility
and a grounded demonstration question; it is not a latency benchmark or a
representative government-document evaluation. No documents were reprocessed.
The ordinary hybrid baseline also returned that supported answer without
warnings: 12 trace stages, about 473 MiB peak resident memory, and 39.0 seconds
including loading the same corpus in another fresh container.

## Code boundaries

- `osii.rag.strategies.tracing`: shared execution record and bounded capture.
- `osii.rag.strategies.experiments` and `haystack`: optional trace instrumentation
  around candidate selection, reranking, and context assembly.
- `osii.search.engine`: optional observations for actual retrieval operations;
  ordinary callers retain their existing interface and behavior.
- `osii.rag.strategies.evaluation`: independent, deterministic pilot metrics.
- `osii.server.rag`: authenticated-principal, PostgreSQL, model, and budget composition.
- `features/chat/components/AgentTraceViewer.tsx` and `traceTypes.ts`: reusable
  presentation over typed records; no database, endpoints, or account management.
- `features/chat/components/AdvancedChat.tsx`: Core-client chat/comparison composition,
  mounted by the hosted Workspace with explicit source-navigation callbacks.

API entry points are authenticated `GET /api/chat/profiles`, `POST /api/chat`
with `profile_id`, and `POST /api/chat/compare` with two or three distinct
`profile_ids`. The existing session and CSRF requirements apply. An execution
failure returns `status: error` with its trace; a configuration/input error or
changed corpus uses the corresponding HTTP error response. No processing jobs,
source mutations, new accounts, or telemetry services are created by a chat run.
