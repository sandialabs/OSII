"""Shared profile execution over caller-bound retrieval/generation adapters."""
from dataclasses import dataclass
from itertools import islice

from .contracts import Decider, Evidence, Limits, Question, RankedEvidence, Reranker, RerankRequest, Result, Retriever, StrategyError
from .profiles import Profile
from .reranking import rerank_evidence


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
                reranker: Reranker | None = None) -> Experiment:
    if profile.rerank and reranker is None:
        raise StrategyError("This profile requires a configured Core RAG reranker")
    from .haystack import run
    events = []

    def bounded_retrieve(query: str, *, top_k: int):
        candidates, characters, seen = [], 0, set()
        for item in islice(retrieve(query, top_k=profile.candidates), profile.candidates):
            if not isinstance(item, Evidence):
                raise StrategyError("Retriever must return Evidence records")
            if item.id in seen:
                continue
            seen.add(item.id)
            if characters + len(item.text) <= 64000:
                candidates.append(item)
                characters += len(item.text)
        request = RerankRequest(query, tuple(candidates), top_k=top_k)
        ranked = rerank_evidence(request, reranker if profile.rerank else None)
        events.append(RetrievalEvent(query, tuple(e.id for e in candidates), tuple(e.id for e in ranked.evidence),
                                     ranked.ranking, ranked.applied))
        return ranked.evidence

    result = run(question, retrieve=bounded_retrieve, decide=decide, strategy=profile.strategy,
                 limits=Limits(max_retrievals=profile.rounds, max_model_calls=profile.rounds,
                               top_k=profile.evidence, max_evidence=24))
    return Experiment(profile.id, result, tuple(events))
