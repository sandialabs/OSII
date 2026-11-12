import importlib
import json
import subprocess
import sys
import time

import pytest

from osii.rag.strategies import Context, Decision, Evidence, Limits, Question, Scope, StrategyError
from osii.rag.strategies.adapters import ChatDecider, CoreRetriever
from osii.rag.strategies.haystack import run


def evidence(key, text="A grounded neutron detector excerpt.", **kwargs):
    return Evidence(key, "file-"+key, text, source_relpath=key+".pdf", **kwargs)


def test_iterative_retrieval_gathers_missing_evidence_preserving_geometry():
    first = evidence("a", corpus_revision="1")
    second = evidence("b", "The calibration source is 241Am.", representation="tesseract:v1",
        char_start=5, char_end=36, source_origin={"page": 2, "bbox": [0.1, 0.2, 0.5, 0.6]}, corpus_revision="1")
    queries=[]
    def retrieve(query, *, top_k):
        queries.append(query)
        return [first] if len(queries)==1 else [first,second]
    def decide(context):
        return Decision("retrieve", query="calibration isotope") if len(context.queries)==1 else Decision("answer", answer=second.text, citation_ids=(second.id,))
    result = run(Question("Which source?", Scope("collection", "private-id")), retrieve=retrieve, decide=decide)
    assert queries == ["Which source?", "calibration isotope"]
    assert result.stop_reason == "answered" and result.retrieval_calls == result.model_calls == 2
    assert result.citations == (second,) and result.citations[0].source_origin["bbox"] == [0.1,0.2,0.5,0.6]
    assert [s.added_ids for s in result.steps] == [("a",),("b",)]


@pytest.mark.parametrize("limits,reason,calls", [
    (Limits(max_retrievals=2), "retrieval_limit", 2),
    (Limits(max_model_calls=1), "model_call_limit", 1),
])
def test_loop_stops_at_budget_instead_of_accepting_unsupported_answer(limits,reason,calls):
    queries=[]
    def retrieve(query, *, top_k):
        queries.append(query); return []
    result = run(Question("Question"), retrieve=retrieve,
        decide=lambda ctx: Decision("retrieve",query=f"different query {len(ctx.queries)}"), limits=limits)
    assert result.stop_reason == reason and len(queries) == calls
    assert result.citations == () and result.model_calls == calls


def test_single_pass_does_not_follow_rewrite_and_duplicate_queries_stop():
    def retrieve(query, *, top_k): return [evidence("a")]
    decide=lambda ctx: Decision("retrieve",query="Question")
    baseline=run(Question("Question"),retrieve=retrieve,decide=decide,strategy="single-pass")
    iterative=run(Question("Question"),retrieve=retrieve,decide=decide)
    assert baseline.retrieval_calls == baseline.model_calls == 1
    assert iterative.retrieval_calls == iterative.model_calls == 1 and iterative.stop_reason == "repeated_query"


def test_context_and_candidate_limits_keep_whole_original_spans():
    rows=[evidence(str(i),"x"*70,char_start=10,char_end=80) for i in range(8)]
    seen=[]
    def decide(context):
        seen.append(context.evidence); return Decision("abstain")
    result=run(Question("q"),retrieve=lambda q,**kw: rows,decide=decide,
        limits=Limits(top_k=3,max_evidence=2,max_context_chars=100))
    assert seen == [(rows[0],)] and result.evidence[0].char_end == 80


def test_cooperative_deadline_rejects_late_generation():
    def decide(ctx):
        time.sleep(0.02)
        return Decision("answer",answer="Too late",citation_ids=("a",))
    result=run(Question("q"),retrieve=lambda q,**kw: [evidence("a")],decide=decide,limits=Limits(deadline_seconds=0.01))
    assert result.stop_reason == "deadline" and not result.citations


@pytest.mark.parametrize("ids", [(),("invented",)])
def test_invented_or_missing_citations_are_never_returned(ids):
    with pytest.raises(Exception,match="must cite only evidence"):
        run(Question("q"),retrieve=lambda q,**kw: [evidence("a")],
            decide=lambda ctx: Decision("answer",answer="Claim",citation_ids=ids))


def test_revision_change_is_refused():
    def retrieve(q,**kw): return [evidence("a",corpus_revision="1" if q=="q" else "2")]
    with pytest.raises(Exception,match="Corpus changed"):
        run(Question("q"),retrieve=retrieve,decide=lambda ctx: Decision("retrieve",query="other"))


def test_contract_import_does_not_load_storage_web_or_framework():
    code="from osii.rag.strategies import Evidence; import sys; assert not ({'faiss','fastapi','sqlalchemy','haystack','osii.rag.service'} & sys.modules.keys())"
    subprocess.run([sys.executable,"-c",code],check=True)
    # Preserve the old package's public imports for existing clients.
    from osii.rag import ChatRequest, RagRetrievalError
    assert ChatRequest and issubclass(RagRetrievalError,RuntimeError)


class Response:
    ok=True
    is_redirect=False
    status_code=200
    def __init__(self,data): self.data=data
    def json(self): return self.data


class Session:
    def __init__(self,responses): self.responses=list(responses); self.calls=[]
    def post(self,url,**kwargs):
        self.calls.append((url,kwargs))
        return self.responses.pop(0)


def test_core_adapter_freezes_private_scope_and_csrf_on_every_query():
    row={"file_id":"f","chunk_id":"c","snippet":"Evidence","char_start":0,"char_end":8,"source_origin":{"page":1}}
    session=Session([Response({"csrf_token":"synthetic-csrf","user":{}}),Response({"results":[row],"corpus_revision":1}),Response({"results":[],"corpus_revision":2})])
    retrieve=CoreRetriever("https://core.test",Scope("collection","private-id"),session=session)
    retrieve.login("user","synthetic-password")
    assert retrieve("query",top_k=3)[0].source_origin == {"page":1}
    with pytest.raises(StrategyError,match="revision changed"):
        retrieve("scope=root",top_k=3)
    for _,call in session.calls[1:]:
        assert call["json"]["scope"] == {"scope_type":"collection","collection_id":"private-id"}
        assert call["headers"]["X-CSRF-Token"] == "synthetic-csrf"
        assert not call["allow_redirects"]


@pytest.mark.parametrize("url",["http://public.example","https://user:secret@host","https://host?key=secret"])
def test_endpoint_credentials_and_insecure_remote_urls_refused(url):
    with pytest.raises(StrategyError): CoreRetriever(url,Scope())


def test_chat_adapter_uses_exact_model_and_rejects_scope_or_tool_actions():
    session=Session([Response({"model":"gemma4","choices":[{"message":{"content":json.dumps({"action":"retrieve","query":"isotope","scope":"root"})}}]})])
    model=ChatDecider("https://models.test/v1","gemma4",session=session)
    with pytest.raises(StrategyError,match="invalid decision"):
        model(Context(Question("q"),(),("q",),True,100))
    assert len(session.calls)==1
    call=session.calls[0][1]
    assert call["json"]["model"]=="gemma4" and call["json"]["max_tokens"]==100
    assert "tools" not in call["json"]


def test_demo_is_offline_and_cli_requires_explicit_model_calls():
    from osii.rag.strategies.__main__ import demo
    assert demo("single-pass").stop_reason == "abstained"
    result=demo("iterative")
    assert result.stop_reason == "answered" and result.citations[0].file_id == "isotopes"
    result=subprocess.run([sys.executable,"-m","osii.rag.strategies","q","--api-url","https://core.test"],capture_output=True,text=True)
    assert result.returncode==2 and "--allow-model-calls" in result.stderr
