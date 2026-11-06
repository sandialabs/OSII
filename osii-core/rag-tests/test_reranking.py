"""Reranking may change selection/order, but never the underlying source evidence."""
import pytest

from osii.rag.strategies import Evidence, RankedEvidence, RerankRequest, StrategyError
from osii.rag.strategies.reranking import rerank_evidence


def candidates():
    return (
        Evidence("a", "file-a", "First original excerpt", representation="text-layer:v1", char_start=5, char_end=27),
        Evidence("b", "file-b", "OCR excerpt", representation="ocr:v2", char_start=0, char_end=11,
                 source_origin={"page": 2, "bbox": [0.1, 0.2, 0.3, 0.4]}),
    )


def test_reranking_preserves_original_representation_spans_and_nested_geometry():
    original = candidates()
    def score(request):
        request.candidates[1].source_origin["bbox"][0] = 999
        return [RankedEvidence("b", 7.2), RankedEvidence("a", -3.5)]
    result = rerank_evidence(RerankRequest("query", original), score)
    assert result.applied
    assert result.evidence[0] is original[1] and result.evidence[1] is original[0]
    assert result.evidence[0].representation == "ocr:v2"
    assert result.evidence[0].source_origin["bbox"][0] == 0.1
    assert [item.score for item in result.ranking] == [7.2, -3.5]


def test_disabled_and_empty_reranking_do_not_invoke_an_endpoint():
    original = candidates()
    result = rerank_evidence(RerankRequest("query", original, top_k=1))
    assert result.evidence == original[:1] and not result.applied
    def forbidden(request): pytest.fail("Empty candidates must not invoke a model")
    assert not rerank_evidence(RerankRequest("query", ()), forbidden).applied


@pytest.mark.parametrize("scores", [
    [RankedEvidence("outside-scope", 1)],
    [RankedEvidence("a", 1), RankedEvidence("a", 2)],
    [RankedEvidence("a", 1), RankedEvidence("b", 2), RankedEvidence("third", 3)],
    [{"evidence_id": "a", "text": "Fabricated text", "score": 1}],
])
def test_foreign_duplicate_excess_and_rewritten_evidence_are_rejected(scores):
    with pytest.raises(StrategyError):
        rerank_evidence(RerankRequest("query", candidates(), top_k=2), lambda _: scores)


def test_ties_preserve_candidate_order_and_an_explicit_empty_ranking_is_kept():
    request = RerankRequest("query", candidates())
    result = rerank_evidence(request, lambda _: [RankedEvidence("b", 1), RankedEvidence("a", 1)])
    assert result.evidence == request.candidates
    assert rerank_evidence(request, lambda _: []).evidence == ()


@pytest.mark.parametrize("score", [float("nan"), float("inf"), "1", True])
def test_invalid_scores_are_rejected(score):
    with pytest.raises(StrategyError): RankedEvidence("a", score)


def test_requests_are_bounded_and_errors_do_not_silently_disable_reranking():
    one = candidates()[0]
    for kwargs in ({"candidates": (one,)*51}, {"candidates": (one,one)},
                   {"candidates": (Evidence("long", "file", "x"*64001),)},
                   {"candidates": candidates(), "top_k": 0}):
        with pytest.raises(StrategyError): RerankRequest("query", **kwargs)
    def unavailable(request): raise RuntimeError("Reranker unavailable")
    with pytest.raises(RuntimeError, match="unavailable"):
        rerank_evidence(RerankRequest("query", candidates()), unavailable)
