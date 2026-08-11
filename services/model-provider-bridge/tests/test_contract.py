from fastapi.testclient import TestClient

from app.main import CLIENTS, app


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
