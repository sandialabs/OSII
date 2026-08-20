from fastapi.testclient import TestClient
import pytest
import requests

from app.main import CLIENTS, DEFAULT_SHIRTY_CHAT_MODEL, app
from tests.fake_shirty_server import app as fake_shirty_app


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


def test_shirty_extraction_uses_documented_http_contract(monkeypatch, tmp_path):
    monkeypatch.setenv("OSII_ROOT", str(tmp_path))
    seen = {}

    def fake_upload(path, **kwargs):
        seen["path"] = path
        seen.update(kwargs)
        return {"text": "Grounded Textract output."}

    monkeypatch.setattr(CLIENTS["shirty"], "upload", fake_upload)
    client = TestClient(app)
    descriptor = client.get("/shirty/extractor/v1/descriptor").json()
    response = client.post(
        "/shirty/extractor/v1/extract",
        json={
            "request_id": "extract-1",
            "document": {
                "filename": "report.pdf",
                "media_type": "application/pdf",
                "content_base64": "JVBERi0xLjQ=",
            },
        },
    )

    assert descriptor["name"] == "corporate.shirty-textract"
    assert response.status_code == 200
    assert seen["path"] == "/extract/textract/create"
    assert seen["filename"] == "report.pdf"
    assert response.json()["segments"][0]["text"] == "Grounded Textract output."
    assert response.json()["document_metadata"]["endpoint_type"] == "shirty-textract-http"


def test_shirty_chat_and_synthesis_use_openai_compatible_route(monkeypatch, tmp_path):
    monkeypatch.setenv("OSII_ROOT", str(tmp_path))
    monkeypatch.delenv("SHIRTY_CHAT_MODEL", raising=False)
    monkeypatch.delenv("SHIRTY_SYNTHESIS_MODEL", raising=False)
    calls = []

    def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs["payload"]))
        return {
            "model": kwargs["payload"]["model"],
            "choices": [
                {"message": {"content": "# Shirty-grounded output"}, "finish_reason": "stop"}
            ],
        }

    monkeypatch.setattr(CLIENTS["shirty"], "request", fake_request)
    client = TestClient(app)
    descriptor = client.get("/shirty/synthesizer/v1/descriptor").json()
    synthesis = client.post(
        "/shirty/synthesizer/v1/synthesize",
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
        "/shirty/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "Hello"}]},
    )

    assert descriptor["name"] == "corporate.shirty-synthesis"
    assert synthesis.status_code == 200
    assert synthesis.json()["metadata"]["provider"] == "shirty"
    assert chat.status_code == 200
    assert chat.json()["provider"] == "shirty"
    assert all(path == "/chat/completions" for _, path, _ in calls)
    assert all(payload["model"] == DEFAULT_SHIRTY_CHAT_MODEL for _, _, payload in calls)
    assert client.get("/shirty/embedder/v1/descriptor").status_code == 404


def test_shirty_http_aliases_and_multipart_upload(monkeypatch, tmp_path):
    monkeypatch.setenv("OSII_ROOT", str(tmp_path))
    monkeypatch.delenv("SHIRTY_BASE_URL", raising=False)
    monkeypatch.delenv("SHIRTY_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://shirty.example.test/api/v1")
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
            return {"text": "extracted"}

    def fake_post(url, **kwargs):
        seen["url"] = url
        seen.update(kwargs)
        return Response()

    monkeypatch.setattr(requests, "post", fake_post)
    payload = CLIENTS["shirty"].upload(
        "/extract/textract/create",
        filename="sample.pdf",
        media_type="application/pdf",
        content=b"pdf",
    )

    assert payload["text"] == "extracted"
    assert seen["url"] == "https://shirty.example.test/api/v1/extract/textract/create"
    assert seen["headers"]["Authorization"] == "Bearer alias-key"
    assert "Content-Type" not in seen["headers"]
    assert seen["files"]["file"] == ("sample.pdf", b"pdf", "application/pdf")


def test_fake_shirty_server_enforces_contract():
    client = TestClient(fake_shirty_app)
    assert client.get("/api/v1/models").status_code == 401
    headers = {"Authorization": "Bearer local-emulator-key"}
    models = client.get("/api/v1/models", headers=headers)
    chat = client.post(
        "/api/v1/chat/completions",
        headers=headers,
        json={
            "model": DEFAULT_SHIRTY_CHAT_MODEL,
            "messages": [{"role": "user", "content": "Hello"}],
        },
    )
    extraction = client.post(
        "/api/v1/extract/textract/create",
        headers=headers,
        files={"file": ("notes.txt", b"safe fixture text", "text/plain")},
    )

    assert models.status_code == 200
    assert chat.json()["choices"][0]["message"]["content"]
    assert extraction.json()["text"] == "safe fixture text"
