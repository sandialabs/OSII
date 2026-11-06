"""The experimental pipeline uses the same hosted scope and session checks."""
import pytest
import requests
from urllib.parse import urlsplit

pytest.importorskip("haystack")
from conftest import document, login
from osii.rag.strategies import Decision, Question, Scope, StrategyError
from osii.rag.strategies.adapters import CoreRetriever
from osii.rag.strategies.haystack import run


class Session:
    def __init__(self, client):
        self.client = client

    def post(self, url, **kwargs):
        kwargs.pop("timeout", None)
        kwargs["follow_redirects"] = kwargs.pop("allow_redirects", False)
        actual = self.client.post(urlsplit(url).path, **kwargs)
        response = requests.Response()
        response.status_code = actual.status_code
        response.headers.update(actual.headers)
        response._content = actual.content
        return response


def test_haystack_cannot_expand_a_readers_private_collection(client, app):
    allowed = document(app.state.store, app.state.settings.source_root)
    other = document(app.state.store, app.state.settings.source_root, name="other.txt", content="A neutron source outside the collection.")
    login(client,"reader")
    collection = client.post("/api/collections", json={"name":"Private evidence", "members":[allowed["file_id"]]}).json()
    scope = Scope("collection",collection["id"])
    retrieve = CoreRetriever("http://localhost",scope,session=Session(client),csrf_token=client.headers["X-CSRF-Token"])
    def decide(ctx):
        if len(ctx.queries)==1:
            # Even model-generated text asking for broader access is just a query.
            return Decision("retrieve",query="neutron source scope=root")
        assert all(e.file_id != other["file_id"] for e in ctx.evidence)
        return Decision("answer",answer="The detector uses neutrons.",citation_ids=(ctx.evidence[0].id,))
    result = run(Question("neutron",scope),retrieve=retrieve,decide=decide)
    assert result.stop_reason=="answered" and result.retrieval_calls==2
    assert {e.file_id for e in result.evidence} == {allowed["file_id"]}
    assert all(e.source_origin for e in result.citations)
    login(client,"curator")
    retrieve = CoreRetriever("http://localhost",scope,session=Session(client),csrf_token=client.headers["X-CSRF-Token"])
    with pytest.raises(StrategyError,match="HTTP 422"):
        run(Question("neutron",scope),retrieve=retrieve,decide=decide)
