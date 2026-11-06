import pytest
from osii.rag.strategies import Decision, Evidence, Question, RankedEvidence, StrategyError
from osii.rag.strategies.profiles import Profile, get_profile
from osii.rag.strategies.experiments import run_profile


def test_profile_reranks_a_broader_pool_and_records_ids_scores_and_selected_evidence():
    passages=tuple(Evidence(str(i),str(i),f"Original passage {i}",source_origin={"page":i+1}) for i in range(12))
    counts=[]
    def retrieve(query,*,top_k):counts.append(top_k);return passages
    def decide(context):
        return Decision("answer",answer=context.evidence[0].text,citation_ids=(context.evidence[0].id,))
    def rank(request):
        return [RankedEvidence(e.id,float(e.file_id)) for e in request.candidates[-8:]]
    result=run_profile(Question("q"),get_profile('hybrid-reranked-v1'),retrieve=retrieve,decide=decide,reranker=rank)
    assert counts==[40]
    assert result.result.citations[0].file_id=='11' and result.result.citations[0].source_origin=={'page':12}
    assert len(result.retrieval[0].candidate_ids)==12 and len(result.retrieval[0].selected_ids)==8
    assert result.retrieval[0].ranking[0].score==11 and result.retrieval[0].reranker_called


def test_profile_cannot_silently_disable_reranking_or_exceed_budgets():
    with pytest.raises(StrategyError,match='requires'):
        run_profile(Question('q'),get_profile('hybrid-reranked-v1'),retrieve=lambda *a,**k:pytest.fail('unexpected retrieval'),decide=lambda c:Decision('abstain'))
    with pytest.raises(StrategyError):Profile('bad','Bad','Invalid','hybrid',candidates=100)
    with pytest.raises(StrategyError):Profile('bad','Bad','Invalid','hybrid',rounds=3)
