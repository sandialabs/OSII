import pytest
import requests

from osii.model_endpoints import endpoint_from_environment
from osii.rag.strategies.contracts import Evidence, RerankRequest, StrategyError
from osii.rag.strategies.http_reranker import create_reranker
from osii.rag.strategies.reranking import rerank_evidence


def test_independent_credentials_and_legacy_compatibility():
    env = {"OPENAI_BASE_URL": "https://legacy.test/v1/", "OPENAI_API_KEY": "legacy-key",
           "OSII_CHAT_BASE_URL": "https://chat.test/v1", "OSII_CHAT_API_KEY": "chat-key",
           "OSII_EMBEDDING_BASE_URL": "https://embed.test/v1", "OSII_EMBEDDING_API_KEY": "embed-key"}
    assert endpoint_from_environment("chat", environment=env).api_key == "chat-key"
    assert endpoint_from_environment("embedding", environment=env).api_key == "embed-key"
    assert endpoint_from_environment("rerank", environment=env).base_url == ""
    del env["OSII_EMBEDDING_API_KEY"]
    assert endpoint_from_environment("embedding", environment=env).api_key == ""
    del env["OSII_EMBEDDING_BASE_URL"]
    assert endpoint_from_environment("embedding", environment=env).api_key == "legacy-key"
    assert endpoint_from_environment("embedding", environment=env).base_url == "https://legacy.test/v1"


def test_capability_file_beats_shared_inline_and_missing_file_fails_closed(tmp_path):
    secret = tmp_path / "key"
    secret.write_text("embedding-secret\n")
    env = {"OSII_MODEL_BASE_URL": "https://legacy.test/v1", "OSII_MODEL_API_KEY": "shared-secret",
           "OSII_EMBEDDING_API_KEY_FILE": str(secret)}
    endpoint = endpoint_from_environment("embedding", environment=env)
    assert endpoint.api_key == "embedding-secret"
    assert "secret" not in repr(endpoint) and "secret" not in str(endpoint.public())
    secret.unlink()
    with pytest.raises(ValueError, match="key file") as error:
        endpoint_from_environment("embedding", environment=env)
    assert str(secret) not in str(error.value)


@pytest.mark.parametrize("url", ["https://user:secret@models.test/v1", "https://models.test?key=secret", "file:///private", "https://models.test/#secret"])
def test_invalid_urls_do_not_echo_secrets(url):
    with pytest.raises(ValueError) as error:
        endpoint_from_environment("chat", environment={"OSII_CHAT_BASE_URL": url})
    assert "secret" not in str(error.value)


def request():
    return RerankRequest("query", (Evidence("a", "file-a", "first", char_start=5, char_end=10),
                                   Evidence("b", "file-b", "second", source_origin={"bbox": [1, 2, 3, 4]})), top_k=2)


def configure(monkeypatch):
    monkeypatch.setenv("OSII_RERANK_BASE_URL", "https://rank.test/v2")
    monkeypatch.setenv("OSII_RERANK_MODEL", "exact-ranker")
    monkeypatch.setenv("OSII_RERANK_API_KEY", "rank-key")
    return create_reranker()


class Response:
    ok, is_redirect, status_code = True, False, 200
    def __init__(self, payload):
        self.payload = payload
    def json(self):
        return self.payload


def test_http_reranker_preserves_provenance_and_uses_only_own_key(monkeypatch):
    reranker = configure(monkeypatch)
    calls = []
    monkeypatch.setattr(requests, "post", lambda url, **kwargs: calls.append((url, kwargs)) or Response(
        {"results": [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.2}]}))
    candidates = request()
    ranked = rerank_evidence(candidates, reranker)
    assert ranked.evidence[0] is candidates.candidates[1]
    assert ranked.evidence[0].source_origin == {"bbox": [1, 2, 3, 4]}
    url, call = calls[0]
    assert url == "https://rank.test/v2/rerank"
    assert call["headers"]["Authorization"] == "Bearer rank-key"
    assert call["json"] == {"model": "exact-ranker", "query": "query", "documents": ["first", "second"], "top_n": 2, "return_documents": False}
    assert call["allow_redirects"] is False


@pytest.mark.parametrize("rows", [[{"index": -1, "relevance_score": 1}], [{"index": True, "relevance_score": 1}],
    [{"index": 0, "relevance_score": float("nan")}], [{"index": 0, "relevance_score": "0.5"}],
    [{"index": 0, "relevance_score": 1}] * 2, [{"index": 0, "relevance_score": 1}] * 3])
def test_invalid_rerank_responses_fail(monkeypatch, rows):
    reranker = configure(monkeypatch)
    monkeypatch.setattr(requests, "post", lambda *a, **kw: Response({"results": rows}))
    with pytest.raises(StrategyError):
        reranker(request())


def test_disabled_and_partial_configuration(monkeypatch):
    for name in ("OSII_RERANK_BASE_URL", "OSII_RERANK_MODEL", "OSII_RERANK_API_KEY", "OSII_RERANK_API_KEY_FILE"):
        monkeypatch.delenv(name, raising=False)
    assert create_reranker() is None
    monkeypatch.setenv("OSII_RERANK_MODEL", "ranker")
    with pytest.raises(StrategyError, match="both"):
        create_reranker()


def test_reranker_network_errors_are_sanitized(monkeypatch):
    reranker = configure(monkeypatch)
    def fail(*a, **kw):
        raise requests.ConnectionError("rank-key and private document")
    monkeypatch.setattr(requests, "post", fail)
    with pytest.raises(StrategyError) as error:
        reranker(request())
    assert "rank-key" not in str(error.value) and "private" not in str(error.value)
