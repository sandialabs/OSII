import json
import time

from osii.domain.model_provider_config import selected_processor


class FakeResponse:
    def __init__(self, *, payload=None, lines=None):
        self._payload = payload or {}
        self._lines = lines or []
        self.ok = True
        self.status_code = 200

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None

    def iter_lines(self):
        return iter(self._lines)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_default_ollama_provider_uses_small_us_models(client):
    payload = client.get("/api/admin/model-providers").json()
    provider = next(item for item in payload["providers"] if item["id"] == "ollama-local")
    assert provider["enabled"] is True
    assert provider["embedding_model"] == "all-minilm"
    assert provider["chat_model"] == "llama3.2:1b"
    assert {item["model"] for item in payload["ollama_recommendations"]} == {"all-minilm", "llama3.2:1b"}


def test_explicitly_disabling_model_providers_restores_local_baselines(client, temp_osii_root):
    response = client.put("/api/admin/model-providers/ollama-local", json={
        "type": "ollama",
        "base_url": "http://127.0.0.1:11434",
        "enabled": False,
        "priority": 100,
        "embedding_model": "all-minilm",
        "synthesis_model": "llama3.2:1b",
        "chat_model": "llama3.2:1b",
        "credential_env": "",
    })
    assert response.status_code == 200
    assert selected_processor("embedder", osii_root=temp_osii_root) == "local.hashing"
    assert selected_processor("synthesizer", osii_root=temp_osii_root) == "local.extractive-preview"


def test_model_provider_configuration_never_persists_secret(client, temp_osii_root, monkeypatch):
    monkeypatch.setenv("MY_CORPORATE_KEY", "super-secret-value")
    response = client.put("/api/admin/model-providers/corporate", json={
        "id": "corporate",
        "type": "shirty",
        "base_url": "https://models.example.test/v1",
        "enabled": True,
        "priority": 10,
        "embedding_model": "embed-v1",
        "synthesis_model": "chat-v1",
        "chat_model": "chat-v1",
        "credential_env": "MY_CORPORATE_KEY",
    })
    assert response.status_code == 200
    assert response.json()["provider"]["credential_present"] is True
    raw = (temp_osii_root / "state" / "model_providers.json").read_text()
    assert "super-secret-value" not in raw
    assert "MY_CORPORATE_KEY" in raw
    assert selected_processor("embedder", osii_root=temp_osii_root) == "corporate.shirty-embedding"


def test_ollama_models_are_discovered_and_allowlisted_pull_runs(client, monkeypatch):
    monkeypatch.setattr(
        "osii.api.model_provider_routes.requests.get",
        lambda *_, **__: FakeResponse(payload={"models": [{"name": "all-minilm:latest", "size": 46_000_000, "digest": "abc", "details": {"family": "bert", "parameter_size": "22M"}}]}),
    )
    health = client.post("/api/admin/model-providers/ollama-local/health").json()
    assert health["ok"] is True
    assert health["model_details"][0]["parameter_size"] == "22M"

    monkeypatch.setattr(
        "osii.api.model_provider_routes.requests.post",
        lambda *_, **__: FakeResponse(lines=[json.dumps({"status": "pulling manifest"}).encode(), json.dumps({"status": "success", "completed": 10, "total": 10}).encode()]),
    )
    started = client.post("/api/admin/model-providers/ollama-local/models/pull", json={"model": "all-minilm"})
    assert started.status_code == 200
    job = started.json()
    for _ in range(50):
        job = client.get(f"/api/admin/model-providers/ollama-local/models/pull/{job['job_id']}").json()
        if job["status"] not in {"queued", "running"}:
            break
        time.sleep(0.01)
    assert job["status"] == "complete"

    denied = client.post("/api/admin/model-providers/ollama-local/models/pull", json={"model": "deepseek-r1"})
    assert denied.status_code == 403
