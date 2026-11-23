from pathlib import Path

from fastapi.testclient import TestClient

from osii_embeddinggemma import DIMENSIONS, MODEL_ID, PROCESSOR_ID
from osii_embeddinggemma.main import _normalized, app, runtime


def test_processor_contract_distinguishes_queries_from_documents(monkeypatch):
    calls = []

    def embed(texts):
        calls.extend(texts)
        return [_normalized([1.0] * 768) for _ in texts]

    monkeypatch.setattr(runtime, "embed", embed)
    monkeypatch.setattr(runtime, "digest", "fixture-weight-digest")
    with TestClient(app) as client:
        descriptor = client.get("/v1/descriptor").json()
        assert descriptor["name"] == PROCESSOR_ID
        assert descriptor["capabilities"]["embedding_input_purpose"]
        response = client.post("/v1/embed", json={
            "request_id": "sample",
            "inputs": [
                {"id": "q", "text": "arid climates", "metadata": {"purpose": "query"}},
                {"id": "d", "text": "Saguaro", "metadata": {"title": "Desert flora"}},
            ],
        })
    assert response.status_code == 200, response.text
    assert calls == [
        "task: search result | query: arid climates",
        "title: Desert flora | text: Saguaro",
    ]
    payload = response.json()
    assert payload["model"] == MODEL_ID
    assert payload["normalized"]
    assert payload["metadata"]["semantic"]
    assert payload["metadata"]["model_digest"] == "fixture-weight-digest"
    assert [item["id"] for item in payload["vectors"]] == ["q", "d"]
    assert all(item["dimensions"] == DIMENSIONS for item in payload["vectors"])


def test_missing_assets_do_not_prevent_service_start(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OSII_EMBEDDINGGEMMA_WEIGHTS", str(tmp_path / "missing.gguf"))
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 503
        rejected = client.post("/v1/embed", json={
            "request_id": "sample",
            "inputs": [{"id": "d", "text": "Saguaro"}],
        })
        assert rejected.status_code == 503
