"""Shared profile execution over caller-bound retrieval/generation adapters."""
from dataclasses import asdict, dataclass
from itertools import islice
from contextlib import nullcontext

from .contracts import Decider, Evidence, Limits, Question, RankedEvidence, Reranker, RerankRequest, Result, Retriever, StrategyError
from .profiles import Profile
from .reranking import rerank_evidence
from .tracing import AgentTrace


@dataclass(frozen=True)
class RetrievalEvent:
    query: str
    candidate_ids: tuple[str, ...]
    selected_ids: tuple[str, ...]
    ranking: tuple[RankedEvidence, ...] = ()
    reranker_called: bool = False


@dataclass(frozen=True)
class Experiment:
    profile_id: str
    result: Result
    retrieval: tuple[RetrievalEvent, ...]


def run_profile(question: Question, profile: Profile, *, retrieve: Retriever, decide: Decider,
                reranker: Reranker | None = None, trace: AgentTrace | None = None) -> Experiment:
    if profile.rerank and reranker is None:
        raise StrategyError("This profile requires a configured Core RAG reranker")
    from .haystack import run
    events = []

    def bounded_retrieve(query: str, *, top_k: int):
        candidates, characters, seen = [], 0, set()
        excluded = []
        for item in islice(retrieve(query, top_k=profile.candidates), profile.candidates):
            if not isinstance(item, Evidence):
                raise StrategyError("Retriever must return Evidence records")
            if item.id in seen:
                excluded.append({"id": item.id, "reason": "duplicate identity"})
                continue
            seen.add(item.id)
            if characters + len(item.text) <= 64000:
                candidates.append(item)
                characters += len(item.text)
            else:
                excluded.append({"id": item.id, "reason": "candidate text budget"})
        request = RerankRequest(query, tuple(candidates), top_k=top_k)
        with (trace.span("rerank" if profile.rerank else "candidate_selection",
                         "Rerank candidates" if profile.rerank else "Select candidates", query=query,
                         input_count=len(candidates) + len(excluded), top_k=top_k) if trace else nullcontext()) as stage:
            ranked = rerank_evidence(request, reranker if profile.rerank else None)
            if stage:
                scores = {row.evidence_id: row.score for row in ranked.ranking}
                stage.items = [{**asdict(item), "rank": i, **({"score": scores[item.id]} if item.id in scores else {})}
                               for i, item in enumerate(ranked.evidence, 1)]
                chosen = {item.id for item in ranked.evidence}
                stage.excluded = excluded + [{"id": item.id, "file_id": item.file_id,
                    "reason": "reranker not selected" if profile.rerank else "candidate count limit"}
                    for item in candidates if item.id not in chosen]
                stage.outputs.update(output_count=len(ranked.evidence), reranker_called=ranked.applied)
        events.append(RetrievalEvent(query, tuple(e.id for e in candidates), tuple(e.id for e in ranked.evidence),
                                     ranked.ranking, ranked.applied))
        return ranked.evidence

    result = run(question, retrieve=bounded_retrieve, decide=decide, strategy=profile.strategy,
                 limits=Limits(max_retrievals=profile.rounds, max_model_calls=profile.rounds,
                               top_k=profile.evidence, max_evidence=24), trace=trace)
    return Experiment(profile.id, result, tuple(events))
