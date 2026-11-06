"""Bounded optional RAG reranking. No framework, store, or processor dependency."""
from copy import deepcopy
from dataclasses import replace
from itertools import islice

from .contracts import RankedEvidence, Reranker, RerankRequest, RerankResult, StrategyError


def rerank_evidence(request: RerankRequest, reranker: Reranker | None = None) -> RerankResult:
    """Select original evidence by validated scores; never accept replacement text.

    Higher scores rank first; ties preserve input order. An absent reranker is an
    explicit pass-through. Errors propagate, rather than silently changing modes.
    Adapters own network timeouts and model-call accounting. This data contract
    is not a sandbox for arbitrary Python code.
    """
    if reranker is None or not request.candidates:
        return RerankResult(request.candidates[:request.top_k], (), False)
    # Protect nested provenance dictionaries even if custom code mutates its inputs.
    isolated = replace(request, candidates=deepcopy(request.candidates))
    ranking = tuple(islice(reranker(isolated), request.top_k + 1))
    if len(ranking) > request.top_k:
        raise StrategyError("Reranker returned more than top_k scores")
    candidates = {item.id: item for item in request.candidates}
    seen = set()
    for item in ranking:
        if not isinstance(item, RankedEvidence):
            raise StrategyError("Reranker must return RankedEvidence records")
        if item.evidence_id not in candidates or item.evidence_id in seen:
            raise StrategyError("Reranker returned an unknown or duplicate evidence ID")
        seen.add(item.evidence_id)
    order = {item.id: index for index, item in enumerate(request.candidates)}
    ranking = tuple(sorted(ranking, key=lambda item: (-item.score, order[item.evidence_id])))
    return RerankResult(tuple(candidates[item.evidence_id] for item in ranking), ranking, True)
