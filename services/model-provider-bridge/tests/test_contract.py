from fastapi.testclient import TestClient
import pytest
import requests

from app.main import CLIENTS, app
from tests.fake_openai_server import app as fake_openai_app


def test_provider_client_preserves_ollama_context_error(monkeypatch):
    response = requests.Response()
    response.status_code = 400
    response._content = b'{"error":"the input length exceeds the context length"}'

    monkeypatch.setattr(requests, "request", lambda *args, **kwargs: response)
    with pytest.raises(ValueError, match="exceeds the context length"):
        CLIENTS["ollama"].request("POST", "/api/embed", payload={"input": ["long"]})


def test_ollama_embedding_and_synthesis_contract(monkeypatch):
    monkeypatch.setenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
    monkeypatch.setenv("OLLAMA_SYNTHESIS_MODEL", "gemma3:4b")

    def fake_request(method, path, **kwargs):
        if path == "/api/embed":
            return {"model": "nomic-embed-text", "embeddings": [[0.0, 1.0]]}
        if path == "/api/chat":
            return {"message": {"content": "# Grounded preview"}}
        if path == "/api/tags":
            return {"models": [{"name": "nomic-embed-text"}]}
        raise AssertionError(path)

    monkeypatch.setattr(CLIENTS["ollama"], "request", fake_request)
    client = TestClient(app)
    descriptor = client.get("/ollama/embedder/v1/descriptor").json()
    assert descriptor["name"] == "ollama.embedder"
    embedded = client.post("/ollama/embedder/v1/embed", json={"request_id": "r1", "inputs": [{"id": "a", "text": "hello"}]})
    assert embedded.status_code == 200
    assert embedded.json()["vectors"] == [{"id": "a", "vector": [0.0, 1.0], "dimensions": 2}]
    synthesized = client.post("/ollama/synthesizer/v1/synthesize", json={"request_id": "r2", "scope": {"scope_type": "object", "scope_id": "a", "documents": [{"file_id": "a", "filename": "a.txt", "text": "hello"}]}})
    assert synthesized.status_code == 200
    assert synthesized.json()["metadata"]["provider"] == "ollama"


def test_synthesis_passes_wiki_guidance_and_output_limit_to_ollama(monkeypatch, tmp_path):
    monkeypatch.setenv("OSII_ROOT", str(tmp_path))
    seen = {}

    def fake_request(method, path, **kwargs):
        assert path == "/api/chat"
        seen.update(kwargs["payload"])
        return {"message": {"content": "# Demonstration Wiki\n\nGrounded fact [doc-1]."}}

    monkeypatch.setattr(CLIENTS["ollama"], "request", fake_request)
    response = TestClient(app).post(
        "/ollama/synthesizer/v1/synthesize",
        json={
            "request_id": "wiki-1",
            "scope": {
                "scope_type": "object",
                "scope_id": "doc-1",
                "documents": [{"file_id": "doc-1", "filename": "report.txt", "text": "Grounded fact."}],
            },
            "expert_context": "Focus on experimental results.",
            "config": {
                "instructions": "Create a grounded wiki.",
                "max_tokens": 1800,
            },
        },
    )

    assert response.status_code == 200
    assert "Create a grounded wiki." in seen["messages"][0]["content"]
    assert "Focus on experimental results." in seen["messages"][0]["content"]
    assert "SOURCE doc-1" in seen["messages"][0]["content"]
    assert seen["options"]["num_predict"] == 1800


def test_ollama_embedding_has_small_us_model_default(monkeypatch, tmp_path):
    monkeypatch.setenv("OSII_ROOT", str(tmp_path))
    monkeypatch.delenv("OLLAMA_EMBEDDING_MODEL", raising=False)
    seen = {}

    def fake_request(method, path, **kwargs):
        seen.update(kwargs["payload"])
        return {"model": "all-minilm", "embeddings": [[1.0, 0.0]]}

    monkeypatch.setattr(CLIENTS["ollama"], "request", fake_request)
    monkeypatch.setattr("app.main._ollama_model_digest", lambda _: None)
    response = TestClient(app).post("/ollama/embedder/v1/embed", json={"request_id": "r", "inputs": [{"id": "a", "text": "hello"}]})
    assert response.status_code == 200
    assert seen["model"] == "all-minilm"


def test_openai_chat_and_synthesis_use_openai_compatible_route(monkeypatch, tmp_path):
    monkeypatch.setenv("OSII_ROOT", str(tmp_path))
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "openai-chat-v1")
    monkeypatch.setenv("OPENAI_SYNTHESIS_MODEL", "openai-chat-v1")
    calls = []

    def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs["payload"]))
        if path == "/embeddings":
            return {
                "model": kwargs["payload"]["model"],
                "data": [{"index": 0, "embedding": [0.25, 0.75]}],
            }
        return {
            "model": kwargs["payload"]["model"],
            "choices": [
                {"message": {"content": "# OpenAI-compatible-grounded output"}, "finish_reason": "stop"}
            ],
        }

    monkeypatch.setattr(CLIENTS["openai"], "request", fake_request)
    client = TestClient(app)
    descriptor = client.get("/openai/synthesizer/v1/descriptor").json()
    synthesis = client.post(
        "/openai/synthesizer/v1/synthesize",
        json={
            "request_id": "s1",
            "scope": {
                "scope_type": "object",
                "scope_id": "doc-1",
                "documents": [
                    {"file_id": "doc-1", "filename": "report.txt", "text": "Grounded fact."}
                ],
            },
        },
    )
    chat = client.post(
        "/openai/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "Hello"}]},
    )
    embedded = client.post(
        "/openai/embedder/v1/embed",
        json={
            "request_id": "e1",
            "inputs": [{"id": "doc-1", "text": "Grounded fact."}],
            "config": {"model": "openai-embed-v1"},
        },
    )

    assert descriptor["name"] == "openai.synthesizer"
    assert synthesis.status_code == 200
    assert synthesis.json()["metadata"]["provider"] == "openai"
    assert chat.status_code == 200
    assert embedded.status_code == 200
    assert embedded.json()["vectors"][0]["dimensions"] == 2
    assert embedded.json()["metadata"]["endpoint_type"] == "openai-compatible"
    assert chat.json()["provider"] == "openai"
    assert [path for _, path, _ in calls].count("/chat/completions") == 2
    assert [path for _, path, _ in calls].count("/embeddings") == 1


def test_openai_http_uses_standard_environment_variables(monkeypatch, tmp_path):
    monkeypatch.setenv("OSII_ROOT", str(tmp_path))
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openai.example.test/api/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "alias-key")
    seen = {}

    class Response:
        text = ""
        status_code = 200

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"data": []}

    def fake_request(method, url, **kwargs):
        assert method == "GET"
        seen["url"] = url
        seen.update(kwargs)
        return Response()

    monkeypatch.setattr(requests, "request", fake_request)
    payload = CLIENTS["openai"].request("GET", "/models")

    assert payload == {"data": []}
    assert seen["url"] == "https://openai.example.test/api/v1/models"
    assert seen["headers"]["Authorization"] == "Bearer alias-key"


def test_openai_embedding_retries_without_optional_encoding_format(monkeypatch, tmp_path):
    monkeypatch.setenv("OSII_ROOT", str(tmp_path))
    calls = []

    def fake_request(method, path, **kwargs):
        calls.append(kwargs["payload"])
        if "encoding_format" in kwargs["payload"]:
            raise ValueError("optional field is not supported")
        return {"model": "embed-v1", "data": [{"embedding": [1.0, 0.0]}]}

    monkeypatch.setattr(CLIENTS["openai"], "request", fake_request)
    response = TestClient(app).post(
        "/openai/embedder/v1/embed",
        json={
            "request_id": "retry",
            "inputs": [{"id": "doc", "text": "hello"}],
            "config": {"model": "embed-v1"},
        },
    )

    assert response.status_code == 200
    assert len(calls) == 2
    assert "encoding_format" not in calls[1]


def test_fake_openai_server_enforces_contract():
    client = TestClient(fake_openai_app)
    assert client.get("/api/v1/models").status_code == 401
    headers = {"Authorization": "Bearer local-emulator-key"}
    models = client.get("/api/v1/models", headers=headers)
    chat = client.post(
        "/api/v1/chat/completions",
        headers=headers,
        json={
            "model": "fixture-chat-model",
            "messages": [{"role": "user", "content": "Hello"}],
        },
    )
    embeddings = client.post(
        "/api/v1/embeddings",
        headers=headers,
        json={"model": "fixture-embedding-model", "input": ["hello"]},
    )
    assert embeddings.status_code == 200
    assert len(embeddings.json()["data"][0]["embedding"]) == 3

    assert models.status_code == 200
    assert chat.json()["choices"][0]["message"]["content"]
