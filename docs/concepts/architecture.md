# OSII architecture

## Design rule

The OSII core owns canonical persistence. Processors are replaceable compute
services and do not mount or mutate `.osii`.

The dashboard, REST API, and MCP interface are peers over the same logical
resources. A standard artifact written by an enricher must be usable by both a
person in the dashboard and an agent without processor-specific integration.

```text
Dashboard / MCP
      |
      v
OSII API + grounded chat  ----> job worker (migration target)
          |
          +----> extractor services
          +----> synthesizer services
          +----> embedder services
          +----> enricher services
          |
          v
  canonical .osii store
```

## Processor API v1

Every external processor implements:

- `GET /health`
- `GET /v1/descriptor`
- one kind-specific operation: `/v1/extract`, `/v1/synthesize`, `/v1/embed`, or
  `/v1/enrich`

The descriptor declares one processor kind, supported media/scope types,
outputs, and a JSON configuration schema. A process request contains either one
document or one scope snapshot. A response contains text segments and/or typed
artifacts.

Requests are self-contained. Source bytes are base64 encoded when required.
Text-oriented processors receive preferred text and provenance. This makes a
processor independently testable and prevents third-party code from corrupting
the store.

The protocol initially favors simple JSON over throughput. Large-artifact
transport (signed object URLs or multipart streaming) can be added compatibly
after real workload measurements.

## Migration

Core owns the protocol and canonical commit adapters. A processor can run as a
bundled local host, an independently deployed container, or an SME-owned
service without changing how Core validates and persists its response:

1. wrap the implementation with `osii.processor_sdk`, included with OSII;
2. add golden contract tests;
3. contract-test the descriptor and operation;
4. register its service URL; and
5. let Core commit the validated response and provenance.

## RAG ownership

OSII Core owns the complete grounded-answer pipeline under `osii/rag`:

1. validate the requested scope;
2. retrieve lexical, semantic, or hybrid evidence from the canonical corpus;
3. preserve source spans and citations;
4. invoke the selected model method or the local extractive fallback; and
5. return one typed answer with the retrieval mode and actual provider used.

The FastAPI `/api/chat` route is a thin transport adapter over this pipeline.
The dashboard calls that route; there is no separate RAG service or RAG image.
Basic reranking can be a bounded step in this Core pipeline, with a model-heavy
implementation supplied by a stateless processor. Core keeps ownership of the
scope, candidate evidence, provenance, and final citations.

Bounded iterative retrieval is an experimental Core RAG strategy, using the same
authorized evidence boundary as single-pass chat. Broader research agents that
write knowledge products remain separate clients of Core, rather than owners of
canonical persistence. See the shared product direction below.

## Repository boundaries

- `osii-core`: core domain, persistence, API, worker, bounded RAG orchestration,
  and grounded chat
- `osii-core/osii/processor_sdk`: public contracts bundled with OSII and
  service/client helpers owned by Core
- `osii-core/services`: guaranteed local Processor API hosts; independently
  addressable and containerizable despite being grouped with their owner
- `osii-dashboard`: browser application
- `osii-mcp`: agent-facing adapter
- `osii-toolbox`: swappable OCR, dataset, and model
  implementations with independent dependencies and container builds; see
  [Toolbox deployment](../operations/publishing-images.md)
- `osii-demo-notebooks`: paired Python/Jupytext demonstrations for the public
  Core and Processor SDK interfaces

## Trust boundary

Workbench tools register their routes and navigation in one typed frontend
registry, load on demand, and have independent loading/error boundaries. Tools
consume Core APIs through adapters and query hooks; they do not access stores
or model endpoints directly. The topic explorer keeps projection and similarity
in a read-only Core domain service. See
[frontend extension architecture](../extending/frontend-tools.md) for the
review findings, extension workflow, limits, and HTTP contracts.

Processor services should be treated as untrusted compute:

- no OSII data-volume mount;
- only requested documents leave the core;
- configuration is validated against the descriptor schema;
- responses are size-limited and schema-validated;
- the core assigns canonical paths and commits outputs;
- network authentication is required outside a private local network.

## Shared product direction: local and hosted

OSII-local and OSII-server are compositions of the same product. Their storage,
identity, and deployment adapters differ; intake, processor contracts, document
inspection, topic exploration, and RAG strategies should converge on shared code.
`main` keeps the standalone startup and sidecar store. `osii-server` keeps hosted
accounts, PostgreSQL, and OpenShift delivery. `osii-large` has a separate canonical
workstation volume store; neither server nor sidecar migrations apply to it.

Shared work belongs in the existing repository, not a new research server or an
unrelated repository:

| Responsibility | Location | Mode-specific edge |
| --- | --- | --- |
| Typed RAG contracts and experimental strategies | `osii-core/osii/rag/strategies/` | Scope-bound Core retrieval and selected model endpoint |
| Shared topic mathematics | `osii-core/osii/domain/topic_projection.py` | PostgreSQL or local index loading |
| Topic map and response types | `src/features/topics/components/DocumentEmbeddingMap.tsx`, `src/features/topics/types.ts` in the dashboard | API hooks, permissions, and navigation |
| Intake planning, job controls, document representation contracts | Core domain and API; shared dashboard feature components | Persistence and authenticated capabilities |
| Optional extractors, embedders, synthesizers, enrichers | `osii-toolbox/<tool>/` | Independently deployed Processor API service |

Portable changes are isolated commits applied to both branches, with identical
shared source and contract tests. Dependency locks and composition adapters are
maintained per branch. A copied component maintained independently is not a
sharing strategy. Do not import files through sibling checkout paths or merge
server persistence into main. While branches remain separate, use the portable
commit as the shared revision and compare the shared files before release. The
longer-term target is common feature code with small composition roots, rather
than two separately evolving applications. No new package registry or repository
is required for this first step.

### Frontend reuse and administration

Reuse local feature components behind explicit clients/capabilities. Presentational
components receive typed data and callbacks; they do not read store paths, import
PostgreSQL, or choose global endpoints. Session handling and CSRF live in the
hosted client adapter. Shared browser tests should exercise both adapters.

The topic map and deterministic PCA now have shared implementations. The topic
pages, scope hooks, and storage loaders remain separate adapters. Next, extract
local intake selection, readiness, previews, job progress/control panels, and
PDF representation inspection into shared components. Keep setup and dataset
mutations available to hosted administrators/curators according to server policy;
ordinary readers retain browse, private collections, search, and chat.

### Endpoint profiles that resemble the corporate environment

Keep independent chat and embedding profiles; a single OpenRouter endpoint is
not the product boundary. A profile records endpoint type, exact model and
revision, dimensions, normalization/pooling, input limit, secret reference, and
whether calls are metered. Job plans capture a profile revision. Free/unmetered
and paid profiles never silently fall back to one another.

| Role | Target model | Development route |
| --- | --- | --- |
| Lightweight embeddings | `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions) | Explicit Toolbox embedder or compatible model gateway |
| Comparison embeddings | `sentence-transformers/all-mpnet-base-v2` (768 dimensions) | Same contract, separately selected profile |
| Unmetered chat | Corporate `gemma4` deployment | Corporate-compatible endpoint; an explicitly selected OpenRouter Gemma 4 free variant can exercise the public development path |
| Metered chat | `openai/gpt-4.1-mini` | OpenRouter now, corporate endpoint when available |

Use the exact sentence-transformer models for parity experiments; substituting
an unrelated embedding model under their names invalidates comparisons. Pin the
checkpoint and preprocessing, including token truncation, chunking, and
normalization. Equal dimensions alone do not make two embedding spaces compatible.
Confirm the actual corporate Gemma checkpoint/quantization and endpoint protocol
before claiming model equivalence. Public free variants can have different
capacity and quotas. Do not try to host a large Gemma model inside the existing
4 GiB application Droplet.

Toolbox remains the home of experimental implementations. Core owns orchestration,
validation, identity, provenance, and commits. The baseline local hashing embedder
is lexical hashing, not MiniLM. A sentence-transformer Toolbox service should
have an explicit model allowlist, isolated dependencies/model cache, bounded
batches, and the existing `/v1/embed` contract. Frameworks must not create a
second authoritative document store or bypass the Processor API to browse files.

### Staged dataset changes and controllable work

Original files remain read-only. Reorganization initially means logical folders,
labels, collection membership, and catalog/source-reference changes, not physical
file moves or renames. An intake plan previews added, changed, missing, duplicate,
and unaffected documents before work is queued. Removing a source from the mount
is distinct from deleting its stored provenance or a user's private collection.

The target workflow is **scan → draft changes → review → queue → inspect → publish**.
A plan captures the corpus revision, explicit document/representation IDs, source
hashes, processor configurations, model profiles, and estimated work. Applying a
stale plan requires review again. PostgreSQL persists server plans, per-item
checkpoints, progress, audit records, and leases. The standalone store uses its
own adapter. Neither uses the other's operational database.

Port the local cooperative controls: queued, running, pause requested, paused,
cancel requested, cancelled, done, and error; resume/retry retain committed work.
Pause/cancel take effect between safe stages or batches, not by killing a model
request and pretending it was undone. Lease recovery must respect requested
controls. Queue priority and whole-queue pause are distinct from pausing one job.

Re-embedding is a separate operation over stored, selected text/chunks. It must
not require re-extracting originals. Build a new embedding generation keyed by
model/profile revision, representation, chunker configuration, and source/text
fingerprint. Keep the current generation serving queries while the new one is
built and evaluated. Activate a complete generation atomically with its query
embedder; never mix vectors from different spaces. Preserve the previous generation
for explicit rollback and apply retention only through a separate reviewed action.

### OCR representations and document inspection

Retain primary text-layer extraction and `osii-tesseract` OCR as separate,
versioned representations of the same original. OCR is useful even when the PDF
already has text. It must not be restricted to the current server's empty-text
fallback. Processor responses already carry page, normalized bounding boxes,
polygons, confidence, and page dimensions through the Processor SDK.

Core persists source hash, representation ID, processor/configuration revision,
text, segments, character offsets, geometry, and lineage. Reprocessing creates a
new version rather than overwriting another representation's spans. Extractors
receive explicit bounded source bytes and return typed output; they never get a
corpus mount or canonical-store credentials.

Reuse the local PDF page/region renderer and text controls. Let the user select
text layer, Tesseract OCR, or the preferred representation and toggle overlays.
Hits identify their exact representation and page/region. Rotation and coordinate
transforms must align overlays with the rendered original. A confidence score
from OCR is not directly comparable to text-layer quality.

"Best available" is a visible, versioned policy: manual preference first, then
explicit heuristics/quality checks. Keep canonical text and all alternatives
inspectable. Index selected representations independently; optional search across
both fuses/deduplicates hits without treating two versions of one page as
independent evidence. Evaluate OCR choices on labelled questions and region/span
checks rather than assuming that a newer model repairs bad extraction.

### Haystack RAG foundation and next steps

`osii.rag.strategies` is the shared, experimental Python boundary. Contracts do
not import a filesystem store, SQL, HTTP server, or Haystack. Optional Haystack
code builds an actual pipeline with retrieval, decision, and routing components
and a bounded feedback loop. It does not create a Haystack document store.

The first strategies are `single-pass` and `iterative`. The latter accumulates
evidence, asks an explicit model for a focused follow-up query, and can answer
or abstain. A retriever is already bound to an authorized scope. The model has
no file, SQL, shell, write, provider-switching, or scope-changing tool. Core's
HTTP adapter uses normal session authentication/CSRF on every search and checks
revision consistency when the API supplies a corpus revision. The local API does
not yet return that revision; immutable local snapshots are a further adapter
requirement, not a guarantee provided by this first client.

The HTTP adapter currently targets the standalone/server `/api/search` contract.
The workstation volume API has a distinct selection/search contract and needs an
explicit scope-preserving adapter; there is no automatic fallback to sidecars.
The offline demo is usable in all three branches.

Limits cover retrieval count, decision calls, result count, evidence text size,
output tokens, and cooperative elapsed time. Network timeouts remain separately
configured; an in-flight request cannot be forcibly cancelled by the soft deadline.
Keep traces with queries, added evidence IDs, actions, model, usage, stop reason,
and citations. Citation validation proves that IDs were supplied, not that every
sentence is factually entailed. Invalid decisions and provider errors do not
trigger silent paid fallback. Telemetry is disabled by default in this adapter.

Delivery order and acceptance:

1. **Shared foundation (this delivery):** portable RAG contracts, runnable offline
   and Core-API experiments, bounded Haystack loop, shared topic rendering/PCA,
   and regression tests. Existing dashboard chat remains on its current production
   orchestration until the new strategies have been evaluated.
2. **Intake/queue parity:** common plan/progress/control components backed by
   PostgreSQL job/item state; stage logical changes; pause/resume/cancel/retry;
   isolated re-embedding generations with atomic activation. Test lease recovery,
   partial failure, role checks, and unchanged originals.
3. **Toolbox/model and OCR parity:** profile-based routing for the exact embedding
   models and Gemma/GPT choices; deploy the selected Tesseract service; persist
   both representations; share the PDF overlay/representation UI. Test geometry,
   source hashes, provenance, and representation-specific search.
4. **RAG evaluation and rollout:** run single-pass and iterative strategies against
   the same versioned collection and labelled questions. Compare source recall,
   supported citations, abstentions, latency, model calls/tokens, and cost. Add
   decomposition/reranking only when measurements justify them. Opt in to the new
   strategy by a versioned configuration; retain the baseline for comparison.

Framework reference: [Haystack pipeline loops](https://docs.haystack.deepset.ai/docs/pipeline-loops).
Model references: [MiniLM](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2),
[MPNet](https://huggingface.co/sentence-transformers/all-mpnet-base-v2), and
[one public Gemma 4 free variant](https://openrouter.ai/google/gemma-4-31b-it:free).
