# Extend Core RAG strategies

Use this guide for custom retrieval, query decomposition, reranking, context
selection, or iterative question answering. These extend **Core RAG**, not the
Toolbox. Start in OSII-local; the same contracts transfer to the hosted server.

## Boundaries and code locations

Toolbox contains exactly four OSII processor kinds: **extractor, synthesizer,
enricher, embedder**. A reranker is an optional step in a RAG process. It is not
a fifth kind and does not need a Processor SDK descriptor or registration in
Setup's processor list. A RAG pipeline may consume the outputs of those four
components without becoming a processor itself.

| Location under `osii-core/osii/rag/strategies/` | Responsibility |
| --- | --- |
| `contracts.py` | Questions, evidence, scope, limits, decisions, results, and optional reranking contracts |
| `haystack.py` | Bounded single-pass and iterative reference pipelines |
| `reranking.py` | Validate candidate scores and select unchanged original evidence |
| `adapters.py` | Explicit Core HTTP retrieval and compatible chat endpoint clients |
| `__main__.py` | Offline demonstration and opt-in Core-API experiments |

Keep a reusable new strategy in this package, with focused tests under
`osii-core/rag-tests/`. An external Python project can instead import these
contracts and supply callables; it does not need the dashboard, a new service,
or a copy of the OSII store. Keep framework-specific imports behind optional
adapters. The contracts and reranking helper use only the Python standard library.

Storage, identity, and model-hosting concerns belong in adapters. An already
scope-bound retriever supplies candidates to the strategy. PostgreSQL, sidecar,
and volume implementations remain separate; no strategy guesses the active store
or falls back to another store. A local function and a client of an existing
remote reranking service can satisfy the same RAG contract. Remote compute does
not make that client a Toolbox processor.

## Strategy contract

The reference runner accepts `Question`, an authorized `Retriever`, a `Decider`,
`Limits`, and a strategy ID (`single-pass` or `iterative`). A custom strategy can
use the same typed inputs/results in its own orchestrator. The reference runner
is not currently a dynamic plugin registry; adding a new strategy ID there is
an explicit code/test change.

- `Retriever(query, top_k=...)` returns `Evidence` already filtered to the caller's
  permitted root, folder, object, or collection. Models cannot replace that scope.
- `Decider(Context)` returns a `Decision`: retrieve with one follow-up query,
  answer with supporting evidence IDs, or abstain. It does not return SQL, file
  paths to open, arbitrary tools, or a new provider to invoke.
- `Evidence.id` must identify a stable passage and representation/version.
  Preserve file identity, text representation, source path, character spans,
  page/region geometry, and available corpus revision. Character offsets belong
  to the identified representation, not an interchangeable OCR/text-layer string.
- `Result` includes the answer, cited and retrieved evidence, steps, stop reason,
  retrieval/decision call counts, and elapsed time. Treat it as an experiment
  record, not proof that the answer is factually correct.

Configure explicit limits and endpoint/model choices. Never implement silent
fallback from a free/unmetered model to a paid one. Keep adapter timeouts and
usage accounting explicit. The reference runner's `max_model_calls` counts
**decider calls**, not arbitrary model calls made inside custom retrieval or
reranking adapters. Its deadline is cooperative between stages; it cannot kill
an in-flight HTTP request. A composite strategy must account for its additional
calls and set appropriate adapter timeouts.

## Optional reranking contract

```python
from osii.rag.strategies import (
    Evidence, RankedEvidence, RerankRequest, RerankResult, Reranker,
)
from osii.rag.strategies.reranking import rerank_evidence
```

`RerankRequest` contains one query, an immutable tuple of authorized candidate
`Evidence`, and `top_k`. It accepts at most 50 unique candidates, 64,000 candidate
text characters, a 4,000-character query, and `top_k` from 1 to 50. Empty candidates
are allowed and do not invoke a reranker. These are initial contract ceilings,
not recommended settings for every dataset.

A `Reranker` is a callable taking that request and returning at most `top_k`
`RankedEvidence(evidence_id, score)` records. It may return fewer, including none.
Scores must be finite numbers, with higher meaning more relevant. They need not
be probabilities or fall between zero and one. An endpoint adapter must map its
native score direction and identifiers to this contract.

Core's `rerank_evidence` helper:

1. gives the callable isolated copies of the candidate data;
2. rejects unknown IDs, duplicate IDs, invalid records, and excessive results;
3. sorts scores descending, preserving input order for ties; and
4. returns the corresponding **original** evidence objects and validated ranking.

The ranker cannot supply replacement source text, new documents, rewritten spans,
or canonical writes through this interface. Nested provenance changes to its
input copies do not affect Core's originals. This contract is not a sandbox for
untrusted Python code.

Passing no reranker explicitly preserves candidate order and selects the first
`top_k`. An endpoint failure propagates; the helper does not silently disable
reranking or choose another model. A broader strategy may implement a declared,
traceable failure policy. An empty ranking is an explicit result, not a reason
to restore discarded candidates silently.

## Small standalone example

This deterministic scorer demonstrates composition; it is not a recommended
relevance model. No model, endpoint, corpus, or credentials are needed.

```python
from osii.rag.strategies import Evidence, RankedEvidence, RerankRequest
from osii.rag.strategies.reranking import rerank_evidence

candidates = (
    Evidence("overview:0", "overview", "A report about several detectors."),
    Evidence("calibration:0", "calibration", "The calibration source is 241Am."),
)

def score(request):
    ranked = [
        RankedEvidence(item.id, float("241Am" in item.text))
        for item in request.candidates
    ]
    return sorted(ranked, key=lambda item: -item.score)[:request.top_k]

result = rerank_evidence(RerankRequest("Which isotope?", candidates, top_k=1), score)
assert result.applied
assert result.evidence[0] is candidates[1]
assert result.ranking[0].evidence_id == "calibration:0"
```

To experiment with the current Haystack runner, compose this step inside an
already-authorized retrieval callable:

```python
# scoped_retrieve is an adapter you have already bound to one authorized scope.
def retrieve_for_rag(query, *, top_k):
    candidates = tuple(scoped_retrieve(query, top_k=40))
    request = RerankRequest(query, candidates, top_k=top_k)
    return rerank_evidence(request, score).evidence
```

Then pass `retrieve_for_rag` to `haystack.run(..., retrieve=retrieve_for_rag)`.
This seam is available now; the built-in CLI/chat UI does not yet have a reranker
or profile selector. Preserve the ranking separately if your experiment needs
score traces: the current reference `Step` records evidence IDs and decider
usage, not reranker scores or model usage. Full profile/trace integration is a
subsequent change, rather than an implied behavior of this helper.

## Tests and review expectations

Run the shared contract/strategy tests from the repository root:

```bash
uv run --package osii --extra rag-haystack --extra dev python -m pytest osii-core/rag-tests -q
```

A custom strategy should demonstrate scope isolation, unchanged evidence and
geometry, bounded calls/context, explicit stopping/abstention, and truthful
failure/usage traces. Rerankers additionally need tests for foreign and duplicate
IDs, score validity, ties, and absent/failed endpoints. Test with deterministic
adapters first. Once real data exists, compare strategies on the same collection
revision and labelled questions; synthetic examples verify plumbing, not quality.

See [standalone RAG experiments](../operations/runbook-development.md#standalone-shared-rag-experiments)
for the offline Haystack demo and authenticated Core API client, and
[shared product architecture](../concepts/architecture.md#shared-product-direction-local-and-hosted)
for storage, model-profile, and frontend boundaries.
