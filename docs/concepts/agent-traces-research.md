# Agent traces and evaluation for multi-step RAG

Review date: November 10, 2026.

This targeted literature review covers multi-stage retrieval, iterative RAG,
evaluation, human verification, and execution tracing. It draws on primary
research and official framework documentation. Research findings are separated
from proposed OSII behavior. It is not a systematic review or evidence that one
strategy will be best for every OSII dataset.

An **agent trace** is the execution record of a request: its operations, inputs,
outputs, dependencies, timings, decisions, failures, and supporting evidence.
The useful unit of inspection is an individual stage, even when that stage is
ordinary full-text search rather than an LLM call. A fixed RAG pipeline can use
the same trace structure as an iterative agent.

## Findings from the literature

### Coarse retrieval and final top-k selection have different purposes

Clarke, Culpepper, and Moffat describe retrieval cascades beginning with cheap
filtering, including Boolean matching, followed by increasingly detailed ranking.
They distinguish evaluating an unordered candidate set from evaluating a ranked
list. Metrics emphasizing the top of a ranked list are not sufficient to assess
an initial filtering stage. [1]

**OSII implication:** support a broad full-text document search as a first-class
stage. A later stage may retrieve passages within those documents, fuse lexical
and semantic results, rerank candidates, and select a bounded context. `top_k`
belongs to stages that perform ranked selection; it need not define every search
operation. A hard early filter can remove evidence that later ranking cannot
recover. Compare that cascade with alternatives such as parallel lexical and
semantic retrieval rather than assuming the hard filter is always beneficial.

### Iterative retrieval should expose how evidence changes the next search

IRCoT interleaves retrieval with intermediate reasoning because an earlier
result can reveal what needs to be searched for next. Adaptive-RAG chooses
different retrieval effort for questions of different complexity. Their benchmark
results support testing multiple strategies, rather than routing every question
through the most elaborate agent. [2, 3]

Brehme, Ströhle, and Breu examine context-aware evaluation of multi-hop retrieval.
A passage that appears irrelevant alone may be an essential bridge when combined
with another passage. Their ECIR workshop study supports considering accumulated
evidence when evaluating multi-hop results. It does not establish that an LLM
judge is reliable for every domain. [4]

**OSII implication:** record the original and actual follow-up queries, their
parent steps, newly added evidence, and stopping decisions. Evaluate whether an
iteration adds useful support, not simply whether it makes more calls. Preserve
the authorized scope throughout the loop.

### Execution records and quality judgments are separate artifacts

RAGAs distinguishes relevant retrieval, faithful use of context, and generation
quality. ARES evaluates context relevance, answer faithfulness, and answer
relevance, using human annotations to calibrate automated judgments. RAGChecker
adds diagnostic measures including claim recall, context utilization, and noise
sensitivity, helping distinguish retrieval failures from generation failures.
These frameworks provide complementary evaluation approaches, not interchangeable
proofs of correctness. [5, 6, 7]

**OSII implication:** separate recorded facts, human annotations, and automated
evaluations. A trace can establish that a query ran and returned certain passages;
it cannot establish that those passages are relevant or an answer is correct.
Record an evaluator's rubric, model, version, and inputs alongside its judgment.
A raw similarity or reranking score is not automatically a calibrated probability.

### Context assembly and citations require inspection

Lost in the Middle finds that the position of relevant information can affect
model performance on the evaluated tasks and models. ALCE evaluates correctness
and citation quality separately: a response with citations can still contain
unsupported claims or incomplete attribution. [8, 9]

**OSII implication:** retain the exact context order supplied to the answer model,
with evidence IDs, source spans, representation versions, and exclusions caused
by deduplication or context limits. Let a reviewer inspect the evidence associated
with each claim and flag incorrect or incomplete support. Recheck context-order
effects on OSII's selected models rather than treating older results as universal.

### OCR quality must be measured downstream

When Good OCR Is Not Enough studies industrial documents with difficult layouts
and other extraction challenges. Strong character-level OCR scores did not
necessarily predict strong retrieval or generation: structural and semantic
errors still caused downstream failures. [10]

**OSII implication:** preserve text-layer and OCR identities through retrieval,
reranking, context assembly, and citations. A reviewer should be able to open
the original page and bounding boxes for a passage. Compare extraction variants
with other retrieval/model settings held fixed to distinguish extraction,
retrieval, and generation failures.

### Interfaces should enable verification and reveal limits

Sotic and Kamps report a qualitative mixed-methods study of nine participants.
Users often assumed document chat involved exhaustive reading and near-perfect
recall; some treated a failure to find information as evidence of its absence.
The small study motivates interface design, rather than population-wide claims.
Li and Aral's randomized experiment also finds that citations can increase trust
even when incorrect. [11, 12]

**OSII implication:** expose search coverage and actual limits. Distinguish no
matches, insufficient evidence, a reached search budget, and a failed stage.
Provide direct source inspection and actionable annotations. More visual detail
should help verification rather than merely increase perceived authority.

### Structured tracing is established; content capture needs explicit policy

Haystack supports component tracing and custom tracers. Langfuse distinguishes
retrieval, generation, embeddings, evaluation, and other operation types.
OpenTelemetry's GenAI conventions define operation-level telemetry and explicit
content-capture controls; those conventions are still marked Development.
Haystack disables component input/output tracing by default. [13, 14, 15]

Phoenix supports annotations on spans and retrieved documents, from humans,
programmatic checks, or LLM evaluators, and connects annotations to evaluation
datasets. These are useful implementation precedents, not evidence that a
particular tracing product improves OSII's answer quality. [16]

**OSII implication:** own a portable trace contract in Core and adapt it to
observability backends. Automatic Haystack component spans will not reveal
internal filtering or ranking inside a composite OSII retriever unless those
operations also emit events. Keep large or sensitive content in controlled
artifacts referenced from lightweight telemetry when appropriate.

## Proposed inspection and evaluation model

The following is an OSII design recommendation synthesized from the research.
It is not an existing implementation specification.

| Stage | Trace contents | Evaluation focus |
| --- | --- | --- |
| Coarse full-text search | Exact query, matching rules, scope/filters, document IDs, match count and whether exact, limits reached | Coverage of relevant documents; reduction in candidate space |
| Passage retrieval | Documents searched, passages returned, representation/version, raw scores and ranks | Recall@k against labeled support; ranking quality where applicable |
| Fusion and reranking | Input lists, score meanings, rank changes, selected and rejected IDs | Ranking improvement and supporting evidence lost |
| Iterative search | Follow-up query, parent step, accumulated and newly added evidence, stop reason | Additional useful support per iteration and effort |
| Context assembly | Actual passage order, deduplication, omitted evidence and budget decisions | Coverage of required evidence, redundancy, and context utilization |
| Answer generation | Model/configuration, supplied context, answer, citation mapping | Correctness, completeness, grounded claims and appropriate abstention |
| Run as a whole | Stage timings, status, errors, model calls, available token/cost usage | Quality versus latency, cost, and failure rate |

Recall measures coverage against known relevant evidence. With incomplete labels,
it is coverage against that labeled set, not a guarantee of corpus-wide recall.
Without reference labels, display that recall is not measured. Precision@k, MRR,
and nDCG answer different questions about ranked results; choose metrics that
match the stage and task. Haystack provides statistical evaluation components
and recommends keeping evaluation independently runnable so stored outputs can
be evaluated without rerunning the application. [17]

Use answerable, multi-hop, unanswerable, and OCR-sensitive questions when those
categories occur in the intended corpus. Retain exact supporting passages and
acceptable answers. Synthetic tests verify control flow and trace integrity;
they do not establish real-corpus quality. Report results per question and task
category, with failures, rather than only an aggregate score. Keep a held-out
evaluation set when tuning strategies and calibrate automated judges with human
review. These are proposed evaluation practices for OSII, not measured results.

## Proposed agent trace viewer

The user-facing view can summarize searches, evidence, citations, and limitations.
A detailed development/reviewer view should provide:

- An execution tree and timeline, including branches, iterations, failures, and
  per-stage timing and available cost.
- A stage inspector with inputs, outputs, configuration, and searchable candidate
  tables. Distinguish total matches, returned results, retained artifacts, and
  displayed samples; mark unknown totals and truncation explicitly.
- Evidence lineage showing where a document or passage entered, changed rank,
  was discarded, entered context, or supported a citation. Preserve parent
  document-to-passage relationships and reasons for exclusions.
- Source navigation to the exact representation, page, text span, and available
  geometry, including OCR comparison.
- Human and automated annotations attached to a run, stage, passage, or claim,
  without rewriting the original execution record.
- Comparisons using the same question, scope, history, corpus/index revision,
  and captured settings, with changed parameters identified. Record actual
  provider/model responses; replay is not a guarantee of identical model output.

OSII-local has no accounts or roles: its detailed view is a local developer or
reviewer feature. Hosted OSII-server can restrict detailed trace access through
its existing account/role policy. The backend must enforce document and trace
permissions; hiding a frontend panel is not authorization. An administrator role
must not accidentally disclose documents, private queries, or collection contents
outside the applicable access policy. Credentials do not belong in trace content.

For large coarse searches, use bounded previews and paginated artifact references
rather than putting every document's full text into one trace response. Define
retention and payload-capture policy explicitly. This keeps the trace useful in
both a local process and a corporate hosted environment.

## OSII implementation starting point and next steps

At review time, shared `osii.rag.strategies` contracts already preserve evidence,
scope, decisions, stopping reasons, and optional reranking. `experiments.py`
records bounded candidate/selected IDs and ranking scores. Local Chat has mode
comparison, evidence inspection, and JSON export. These are useful foundations,
not the complete viewer proposed above. See the
[RAG strategy authoring guide](../extending/rag-strategies.md).

The current `Retriever(query, top_k=...)` contract and compact `Step` records do
not directly describe broad unordered document sets, internal retrieval stages,
every exclusion, or stage-level timings. Candidate IDs recorded by the experiment
wrapper describe its retained bounded pool, not necessarily all earlier matches.
Local read guards detect observed changes but do not supply transactional corpus
snapshots. Missing query-embedding or custom reranker usage must remain explicit.

Recommended implementation order:

1. Specify shared typed trace records and artifact references. Support unordered
   sets, ranked lists, document-to-passage transitions, parent relationships,
   exclusions, errors, budgets, and schema/version identifiers.
2. Instrument executed Core stages, retaining deterministic evidence identity and
   provenance. Keep framework adapters and telemetry export at the edges.
3. Build reusable trace-view components over typed data and callbacks; supply
   local and authenticated hosted transport/persistence adapters separately.
4. Add independent evaluation and annotations, then compare selected advanced
   strategies against a baseline on a labeled corpus. Report measured strengths
   and failures before selecting defaults.

RAG orchestration and reranking remain Core responsibilities. processor modules retains
exactly four processor kinds: extractor, synthesizer, enricher, and embedder.
The trace feature does not introduce a fifth kind, a new authoritative document
store, local user accounts, or a framework dependency in the domain contracts.

## References

References were consulted for the November 10, 2026 review. Framework documentation
and development-stage conventions may change; pin implementation dependencies
and verify adapter behavior against the versions actually deployed.

1. Clarke, C. L. A., Culpepper, J. S., and Moffat, A. (2015 preprint).
   [Assessing Efficiency-Effectiveness Tradeoffs in Multi-Stage Retrieval Systems Without Using Relevance Judgments](https://arxiv.org/abs/1506.00717).
   Primary research on filtering, ranking, and assessing early-stage loss.
2. Trivedi, H., Balasubramanian, N., Khot, T., and Sabharwal, A. (ACL 2023).
   [Interleaving Retrieval with Chain-of-Thought Reasoning for Knowledge-Intensive Multi-Step Questions](https://aclanthology.org/2023.acl-long.557/).
   IRCoT: evidence-dependent iterative retrieval.
3. Jeong, S., et al. (NAACL 2024).
   [Adaptive-RAG: Learning to Adapt Retrieval-Augmented Large Language Models through Question Complexity](https://aclanthology.org/2024.naacl-long.389/).
   Strategy selection and the cost of unnecessary retrieval effort.
4. Brehme, L., Ströhle, T., and Breu, R. (2026; accepted at the ECIR SynIRgy workshop).
   [Evaluating Multi-Hop Reasoning in RAG Systems: A Comparison of LLM-Based Retriever Evaluation Strategies](https://arxiv.org/abs/2604.18234).
   Context-aware evaluation of evidence that matters in combination.
5. Es, S., James, J., Espinosa Anke, L., and Schockaert, S. (EACL 2024).
   [RAGAs: Automated Evaluation of Retrieval Augmented Generation](https://aclanthology.org/2024.eacl-demo.16/).
   Reference-free evaluation across retrieval and generation dimensions.
6. Saad-Falcon, J., Khattab, O., Potts, C., and Zaharia, M. (NAACL 2024).
   [ARES: An Automated Evaluation Framework for Retrieval-Augmented Generation Systems](https://aclanthology.org/2024.naacl-long.20/).
   Component evaluation with automated judges and human calibration.
7. Ru, D., et al. (NeurIPS 2024).
   [RAGChecker: A Fine-grained Framework for Diagnosing Retrieval-Augmented Generation](https://arxiv.org/abs/2408.08067).
   Claim-level diagnostics for retrieval and generation failures.
8. Liu, N. F., et al. (TACL 2024).
   [Lost in the Middle: How Language Models Use Long Contexts](https://aclanthology.org/2024.tacl-1.9/).
   Controlled evaluation of relevant evidence position in model inputs.
9. Gao, T., Yen, H., Yu, J., and Chen, D. (EMNLP 2023).
   [Enabling Large Language Models to Generate Text with Citations](https://aclanthology.org/2023.emnlp-main.398/).
   ALCE: answer correctness and citation quality evaluation.
10. Sun, L., et al. (ACL Industry 2026).
    [When Good OCR Is Not Enough: Benchmarking OCR Robustness for Retrieval-Augmented Generation](https://aclanthology.org/2026.acl-industry.60/).
    Industrial OCR errors and their downstream RAG effects.
11. Sotic, B. N., and Kamps, J. (SIGIR 2026).
    [Information Seeking Behavior in LLM-Based RAG: Mental Models and Missing Information](https://doi.org/10.1145/3805712.3808537).
    Small qualitative study of user assumptions, missing information, and verification.
12. Li, H., and Aral, S. (2025 preprint).
    [Human Trust in AI Search: A Large-Scale Experiment](https://arxiv.org/abs/2504.06435).
    Experimental evidence about citations and trust, including incorrect citations.
13. deepset. [Haystack: Tracing](https://docs.haystack.deepset.ai/docs/tracing).
    Official component tracing, custom tracer, and content-capture documentation.
14. Langfuse. [Observation Types](https://langfuse.com/docs/observability/features/observation-types).
    Official operation types and hierarchical execution inspection.
15. OpenTelemetry.
    [Semantic conventions for generative client AI spans](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md).
    Development-stage operation conventions and sensitive-content capture policy.
16. Arize Phoenix.
    [Annotations Concepts](https://arize.com/docs/phoenix/tracing/concepts-tracing/annotations-concepts).
    Official span/document annotation and evaluation-dataset integration documentation.
17. deepset.
    [Haystack: Statistical Evaluation](https://docs.haystack.deepset.ai/docs/statistical-evaluation).
    Ground-truth retrieval metrics and independently runnable evaluation pipelines.
