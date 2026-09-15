import json
import os
from pathlib import Path
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
    embedder = next(item for item in payload["providers"] if item["id"] == "minilm")
    language = next(item for item in payload["providers"] if item["id"] == "base")
    assert embedder["enabled"] is True
    assert embedder["embedding_model"] == "all-minilm"
    assert language["chat_model"] == "llama3.2:1b"
    assert {item["model"] for item in payload["ollama_recommendations"]} == {"all-minilm", "llama3.2:1b"}


def test_explicitly_disabling_model_providers_restores_local_baselines(client, temp_osii_root):
    response = client.put("/api/admin/model-providers/base", json={
        "type": "ollama",
        "base_url": "http://127.0.0.1:11434",
        "enabled": False,
        "priority": 100,
        "embedding_model": "",
        "synthesis_model": "llama3.2:1b",
        "chat_model": "llama3.2:1b",
        "credential_env": "",
    })
    assert response.status_code == 200
    assert selected_processor("synthesizer", osii_root=temp_osii_root) == "local.extractive-preview"


def test_model_provider_configuration_never_persists_secret(client, temp_osii_root, monkeypatch):
    monkeypatch.setenv("MY_CORPORATE_KEY", "super-secret-value")
    response = client.put("/api/admin/model-providers/corporate", json={
        "id": "corporate",
        "type": "openai",
        "base_url": "https://models.example.test/v1",
        "enabled": True,
        "priority": 10,
        "embedding_model": "embed-v1",
        "synthesis_model": "chat-v1",
        "chat_model": "chat-v1",
        "credential_env": "MY_CORPORATE_KEY",
        "default_chat": True,
        "default_embedding": True,
    })
    assert response.status_code == 200
    assert response.json()["provider"]["credential_present"] is True
    raw = (Path(os.environ["OSII_CONFIG_DIR"]) / "models.yml").read_text()
    assert "super-secret-value" not in raw
    assert "MY_CORPORATE_KEY" in raw
    assert "model: embed-v1" in raw
    assert selected_processor("embedder", osii_root=temp_osii_root) == "openai.embedder"
    assert selected_processor("synthesizer", osii_root=temp_osii_root) == "openai.synthesizer"


def test_additional_connection_only_becomes_default_when_selected(client, temp_osii_root):
    payload = {
        "type": "openai",
        "base_url": "https://premium-models.example.test/v1",
        "enabled": True,
        "priority": 10,
        "embedding_model": "",
        "synthesis_model": "vendor/top-model",
        "chat_model": "vendor/top-model",
        "credential_env": "OPENAI_API_KEY",
        "default_chat": False,
        "default_embedding": False,
    }
    assert client.put("/api/admin/model-providers/top", json=payload).status_code == 200
    assert selected_processor("synthesizer", osii_root=temp_osii_root) == "ollama.synthesizer"

    selected = client.put(
        "/api/admin/model-providers/top",
        json={**payload, "default_chat": True},
    )

    assert selected.status_code == 200
    assert selected.json()["provider"]["default_chat"] is True
    assert selected_processor("synthesizer", osii_root=temp_osii_root) == "openai.synthesizer"


def test_local_env_credential_is_write_only_and_used_for_health(client, temp_osii_root, tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("UNCHANGED=value\n", encoding="utf-8")
    monkeypatch.setenv("OSII_ENV_FILE", str(env_file))
    monkeypatch.setenv("OSII_ALLOW_LOCAL_CONFIG_WRITES", "true")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    saved = client.put("/api/admin/model-providers/openai-demo", json={
        "type": "openai",
        "base_url": "https://openai.example.test/api/v1",
        "enabled": True,
        "priority": 10,
        "embedding_model": "embed-v1",
        "synthesis_model": "chat-v1",
        "chat_model": "chat-v1",
        "credential_env": "OPENAI_API_KEY",
    })
    assert saved.status_code == 200
    response = client.put(
        "/api/admin/model-providers/openai-demo/credential",
        json={"api_key": "saved-secret"},
    )
    assert response.status_code == 200
    assert "saved-secret" not in response.text
    assert "UNCHANGED=value" in env_file.read_text(encoding="utf-8")
    assert 'OPENAI_API_KEY="saved-secret"' in env_file.read_text(encoding="utf-8")
    assert "saved-secret" not in (Path(os.environ["OSII_CONFIG_DIR"]) / "models.yml").read_text()

    seen = {}

    def fake_get(*args, **kwargs):
        seen.update(kwargs["headers"])
        return FakeResponse(payload={"data": [{"id": "embed-v1"}, {"id": "chat-v1"}]})

    monkeypatch.setattr("osii.api.model_provider_routes.requests.get", fake_get)
    health = client.post("/api/admin/model-providers/openai-demo/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True
    assert seen["Authorization"] == "Bearer saved-secret"

    removed = client.delete("/api/admin/model-providers/openai-demo/credential")
    assert removed.status_code == 200
    assert "OPENAI_API_KEY" not in env_file.read_text(encoding="utf-8")


def test_removing_connection_also_forgets_its_locally_saved_key(client, tmp_path, monkeypatch):
    env_file = tmp_path / "secrets.env"
    monkeypatch.setenv("OSII_ENV_FILE", str(env_file))
    monkeypatch.setenv("OSII_ALLOW_LOCAL_CONFIG_WRITES", "true")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client.put("/api/admin/model-providers/top", json={
        "type": "openai",
        "base_url": "https://models.example.test/v1",
        "enabled": True,
        "priority": 10,
        "embedding_model": "",
        "synthesis_model": "chat-v1",
        "chat_model": "chat-v1",
        "credential_env": "OPENAI_API_KEY",
    })
    client.put(
        "/api/admin/model-providers/top/credential",
        json={"api_key": "saved-secret"},
    )

    removed = client.delete("/api/admin/model-providers/top")

    assert removed.status_code == 200
    assert "saved-secret" not in env_file.read_text(encoding="utf-8")


def test_openai_environment_exposes_generic_runtime_defaults(client, monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://models.example.test/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "alias-key")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "embed-v1")
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "chat-v1")

    payload = client.get("/api/admin/model-providers").json()
    provider = next(item for item in payload["providers"] if item["id"] == "openai-compatible")

    assert provider["base_url"] == "https://models.example.test/v1"
    assert provider["enabled"] is True
    assert provider["priority"] == 10
    assert provider["embedding_model"] == "embed-v1"
    assert provider["chat_model"] == "chat-v1"
    assert provider["credential_present"] is True


def test_openai_environment_accepts_container_secret_file(client, monkeypatch, tmp_path):
    secret = tmp_path / "openai_api_key"
    secret.write_text("mounted-secret\n", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY_FILE", str(secret))
    monkeypatch.setenv("OPENAI_BASE_URL", "https://models.example.test/v1")

    payload = client.get("/api/admin/model-providers").json()
    provider = next(item for item in payload["providers"] if item["id"] == "openai-compatible")

    assert provider["credential_present"] is True
    assert "mounted-secret" not in str(payload)


def test_openai_health_validates_selected_embedding_model(client, monkeypatch):
    client.put("/api/admin/model-providers/openai-probe", json={
        "type": "openai",
        "base_url": "https://models.example.test/v1",
        "enabled": True,
        "priority": 10,
        "embedding_model": "embed-v1",
        "synthesis_model": "chat-v1",
        "chat_model": "chat-v1",
        "credential_env": "OPENAI_API_KEY",
    })
    monkeypatch.setattr(
        "osii.api.model_provider_routes.requests.get",
        lambda *_, **__: FakeResponse(payload={"data": [{"id": "embed-v1"}, {"id": "chat-v1"}]}),
    )
    monkeypatch.setattr(
        "osii.api.model_provider_routes.requests.post",
        lambda *_, **__: FakeResponse(payload={"data": [{"embedding": [0.1, 0.2, 0.3]}]}),
    )

    health = client.post("/api/admin/model-providers/openai-probe/health").json()

    assert health["ok"] is True
    assert health["capabilities"]["embedding"] == {
        "configured": True,
        "ok": True,
        "model": "embed-v1",
        "dimensions": 3,
        "detail": "Validated a 3-dimensional embedding vector.",
    }


def test_ollama_models_are_discovered_and_allowlisted_pull_runs(client, monkeypatch):
    monkeypatch.setattr(
        "osii.api.model_provider_routes.requests.post",
        lambda *_, **__: FakeResponse(payload={"embeddings": [[0.1, 0.2, 0.3]]}),
    )
    monkeypatch.setattr(
        "osii.api.model_provider_routes.requests.get",
        lambda *_, **__: FakeResponse(payload={"models": [{"name": "all-minilm:latest", "size": 46_000_000, "digest": "abc", "details": {"family": "bert", "parameter_size": "22M"}}]}),
    )
    health = client.post("/api/admin/model-providers/minilm/health").json()
    assert health["ok"] is True
    assert health["model_details"][0]["parameter_size"] == "22M"
    assert health["capabilities"]["embedding"] == {
        "configured": True,
        "ok": True,
        "model": "all-minilm",
        "dimensions": 3,
        "detail": "Validated a 3-dimensional embedding vector.",
    }

    monkeypatch.setattr(
        "osii.api.model_provider_routes.requests.post",
        lambda *_, **__: FakeResponse(lines=[json.dumps({"status": "pulling manifest"}).encode(), json.dumps({"status": "success", "completed": 10, "total": 10}).encode()]),
    )
    started = client.post("/api/admin/model-providers/minilm/models/pull", json={"model": "all-minilm"})
    assert started.status_code == 200
    job = started.json()
    for _ in range(50):
        job = client.get(f"/api/admin/model-providers/minilm/models/pull/{job['job_id']}").json()
        if job["status"] not in {"queued", "running"}:
            break
        time.sleep(0.01)
    assert job["status"] == "complete"

    denied = client.post("/api/admin/model-providers/minilm/models/pull", json={"model": "deepseek-r1"})
    assert denied.status_code == 403


def test_ollama_pull_stream_error_is_reported(client, monkeypatch):
    monkeypatch.setattr(
        "osii.api.model_provider_routes.requests.post",
        lambda *_, **__: FakeResponse(
            lines=[json.dumps({"error": "registry access was denied"}).encode()]
        ),
    )

    started = client.post(
        "/api/admin/model-providers/minilm/models/pull",
        json={"model": "all-minilm"},
    )
    assert started.status_code == 200
    job = started.json()
    for _ in range(50):
        job = client.get(
            f"/api/admin/model-providers/minilm/models/pull/{job['job_id']}"
        ).json()
        if job["status"] not in {"queued", "running"}:
            break
        time.sleep(0.01)

    assert job["status"] == "error"
    assert job["status_text"] == "Download failed"
    assert job["detail"] == "registry access was denied"
