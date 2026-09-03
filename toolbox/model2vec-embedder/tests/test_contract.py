import math
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from app.main import LocalModel2VecEmbedder, app
from osii_processor_sdk import EmbeddingRequest

client = TestClient(app)

def test_hashing_contract_determinism_order_and_norm():
    assert client.get("/v1/descriptor").json()["name"] == "local.hashing"
    assert "/v1/embed" in client.get("/openapi.json").json()["paths"]
    payload = {"request_id": "r1", "inputs": [{"id": "b", "text": "alpha beta"}, {"id": "a", "text": "alpha beta"}]}
    first = client.post("/v1/embed", json=payload).json()
    second = client.post("/v1/embed", json=payload).json()
    assert first == second
    assert [row["id"] for row in first["vectors"]] == ["b", "a"]
    assert all(row["dimensions"] == 384 for row in first["vectors"])
    assert math.isclose(sum(x*x for x in first["vectors"][0]["vector"]), 1.0)

def test_invalid_payload_is_422():
    assert client.post("/v1/embed", json={}).status_code == 422


def test_model2vec_uses_staged_model_and_preserves_vector_identity(tmp_path, monkeypatch):
    loaded = []

    class FakeStaticModel:
        @staticmethod
        def from_pretrained(path):
            loaded.append(path)
            return SimpleNamespace(encode=lambda texts: [[3.0, 4.0] for _ in texts])

    monkeypatch.setitem(sys.modules, "model2vec", SimpleNamespace(StaticModel=FakeStaticModel))
    monkeypatch.setenv("OSII_OFFLINE", "1")
    monkeypatch.setenv("OSII_MODEL2VEC_MODEL", str(tmp_path))
    processor = LocalModel2VecEmbedder()
    response = processor.embed(EmbeddingRequest(
        request_id="staged", inputs=[{"id": "second", "text": "beta"}, {"id": "first", "text": "alpha"}],
    ))
    assert loaded == [str(tmp_path)]
    assert response.processor.name == "local.model2vec"
    assert response.model == str(tmp_path)
    assert response.metadata == {"provider": "model2vec", "semantic": True}
    assert [row.id for row in response.vectors] == ["second", "first"]
    assert all(row.vector == [0.6, 0.8] and row.dimensions == 2 for row in response.vectors)


def test_missing_staged_model_fails_without_fetching(tmp_path, monkeypatch):
    def unexpected_download(*args):
        pytest.fail("Missing staged model must not trigger a download")

    monkeypatch.setitem(sys.modules, "model2vec", SimpleNamespace(
        StaticModel=SimpleNamespace(from_pretrained=unexpected_download),
    ))
    monkeypatch.setenv("OSII_OFFLINE", "1")
    monkeypatch.setenv("OSII_MODEL2VEC_MODEL", str(tmp_path / "missing-model"))
    with pytest.raises(RuntimeError, match="staged model files"):
        LocalModel2VecEmbedder()
