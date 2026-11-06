import pytest
from osii.model_provider import ModelProvider, ProviderError
from osii.model_endpoints import ModelEndpoint


def test_catalog_keeps_api_id_distinct_from_label(monkeypatch):
    provider = ModelProvider("https://endpoint.test/v1", "private")
    monkeypatch.setattr(provider, "request", lambda *a: {"data": [{"id": "vendor/exact-id", "name": "A friendly name"}]})
    assert provider.catalog() == [{"id": "vendor/exact-id", "name": "A friendly name", "capabilities": []}]


def test_non_json_error_is_actionable(monkeypatch):
    import requests
    class Response:
        ok = True
        def json(self):
            raise ValueError("html")
    monkeypatch.setattr(requests, "request", lambda *a, **kw: Response())
    with pytest.raises(ProviderError, match="API base URL"):
        ModelProvider("https://endpoint.test", "private").catalog()


@pytest.mark.parametrize("failure", [429, 503, "network"])
def test_embedding_transient_failure_retries_then_recovers(monkeypatch, failure):
    import requests
    import osii.model_provider as module
    calls, delays = [], []
    class Response:
        ok = True
        def json(self):
            return {"data": [{"index": 0, "embedding": [1, 0]}]}
    class Unavailable:
        ok = False
        status_code = failure
        headers = {"Retry-After": "120"}
    def request(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            if failure == "network":
                raise requests.ConnectionError("private transport detail")
            return Unavailable()
        return Response()
    monkeypatch.setattr(requests, "request", request)
    monkeypatch.setattr(module.time, "sleep", delays.append)
    assert ModelProvider("https://endpoint.test", "private").embed("model", ["text"]) == [[1, 0]]
    assert len(calls) == 2 and delays == ([1] if failure == "network" else [30])


@pytest.mark.parametrize("status, expected_calls", [(400, 1), (401, 1), (429, 3), (503, 3)])
def test_embedding_retries_are_bounded_and_errors_sanitized(monkeypatch, status, expected_calls):
    import requests
    import osii.model_provider as module
    calls = []
    class Response:
        ok = False
        status_code = status
        headers = {}
        text = "private provider response"
    monkeypatch.setattr(requests, "request", lambda *a, **kw: calls.append(a) or Response())
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    with pytest.raises(ProviderError) as exc:
        ModelProvider("https://endpoint.test", "private").embed("model", ["private source"])
    assert len(calls) == expected_calls
    assert "private" not in str(exc.value)


def test_separate_provider_routing_and_catalog_credentials(monkeypatch):
    import requests
    calls = []
    class Response:
        ok, status_code = True, 200
        def __init__(self, payload):
            self.payload = payload
        def json(self):
            return self.payload
    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if method == "GET":
            return Response({"data": [{"id": "exact-id", "name": "Model"}]})
        if url.endswith("/embeddings"):
            return Response({"data": [{"index": 0, "embedding": [1, 0]}]})
        return Response({"choices": [{"message": {"content": "Answer"}}]})
    monkeypatch.setattr(requests, "request", request)
    provider = ModelProvider("https://chat.test/v1", "chat-key",
        embedding_endpoint=ModelEndpoint("https://embedding.test/v1", "embedding-key"))
    assert provider.chat("chat-model", [])[0] == "Answer"
    assert provider.embed("embedding-model", ["query"]) == [[1, 0]]
    assert {tuple(row["capabilities"]) for row in provider.catalog()} == {("chat",), ("embedding",)}
    for _, url, kwargs in calls:
        assert kwargs["headers"]["Authorization"] == ("Bearer chat-key" if url.startswith("https://chat.") else "Bearer embedding-key")
        assert kwargs["allow_redirects"] is False


def test_server_environment_preserves_legacy_and_exposes_no_keys(monkeypatch):
    import os
    from osii.server.config import Settings
    for name in list(os.environ):
        if name.startswith(("OSII_CHAT_", "OSII_EMBEDDING_", "OSII_RERANK_", "OSII_MODEL_", "OPENAI_")):
            monkeypatch.delenv(name)
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://legacy.test/v1")
    monkeypatch.setenv("OSII_MODEL_API_KEY", "private-shared")
    legacy = Settings.environment()
    assert legacy.model_url == "https://legacy.test/v1"
    assert legacy.embedding_endpoint.api_key == "private-shared"
    monkeypatch.setenv("OSII_EMBEDDING_BASE_URL", "https://embedding.test/v1")
    monkeypatch.setenv("OSII_EMBEDDING_API_KEY", "private-embedding")
    settings = Settings.environment()
    assert settings.provider().embedding_provider.key == "private-embedding"
    assert "private" not in str({k: v.public() for k, v in settings.endpoints().items()})
