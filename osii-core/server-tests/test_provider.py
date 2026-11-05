import pytest
from osii.model_provider import ModelProvider, ProviderError


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
