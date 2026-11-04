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
