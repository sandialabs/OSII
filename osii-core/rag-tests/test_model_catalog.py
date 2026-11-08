import pytest
import requests
from osii.model_catalog import CatalogError, discover_models


class Response:
    ok, status_code = True, 200
    def __init__(self, payload): self.payload = payload
    def json(self): return self.payload


def test_catalog_keeps_names_separate_from_identifiers_and_never_invokes_models(monkeypatch):
    calls = []
    def get(url, **kwargs):
        calls.append((url, kwargs))
        return Response({"data": [{"id": "vendor/exact-name", "name": "Friendly model", "architecture": {"output_modalities": ["text"]}}]})
    monkeypatch.setattr(requests, "get", get)
    assert discover_models("https://models.test/v1/", "synthetic-key", capability="chat") == [
        {"id": "vendor/exact-name", "name": "Friendly model", "capabilities": ["chat"]}]
    assert calls[0][0] == "https://models.test/v1/models"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer synthetic-key"
    assert calls[0][1]["allow_redirects"] is False


def test_embedding_discovery_uses_the_openrouter_embedding_catalog(monkeypatch):
    calls = []
    monkeypatch.setattr(requests, "get", lambda url, **kw: calls.append(url) or Response({"data": [{"id": "embed", "name": "Embed"}]}))
    assert discover_models("https://openrouter.ai/api/v1", capability="embedding")[0]["capabilities"] == ["embedding"]
    assert calls == ["https://openrouter.ai/api/v1/embeddings/models"]


def test_ollama_returns_installed_names_without_guessing_capabilities(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda url, **kw: Response({"models": [{"name": "local-model:latest", "model": "local-model:latest"}]}))
    assert discover_models("http://127.0.0.1:11434", protocol="ollama")[0]["id"] == "local-model:latest"


@pytest.mark.parametrize("status", [302, 401, 403, 404, 500])
def test_errors_do_not_echo_credentials_or_provider_bodies(monkeypatch, status):
    response = Response({"error": "synthetic-secret and private response"})
    response.ok, response.status_code = status < 400, status
    monkeypatch.setattr(requests, "get", lambda *a, **kw: response)
    with pytest.raises(CatalogError) as error:
        discover_models("https://models.test/v1", "synthetic-secret")
    assert "synthetic-secret" not in str(error.value) and "private response" not in str(error.value)


def test_unreadable_json_and_transport_failures_are_sanitized(monkeypatch):
    def fail(*args, **kwargs): raise requests.ConnectionError("synthetic-secret")
    monkeypatch.setattr(requests, "get", fail)
    with pytest.raises(CatalogError, match="could not be reached"):
        discover_models("https://models.test/v1")
    monkeypatch.setattr(requests, "get", lambda *a, **kw: Response({"data": "invalid"}))
    with pytest.raises(CatalogError, match="unreadable"):
        discover_models("https://models.test/v1")
