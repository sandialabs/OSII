import pytest
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


def test_catalog_uses_api_ids_and_preserves_display_labels():
    from osii.api.model_provider_routes import _model_details
    models = _model_details({"data": [{"id": "vendor/exact-api-id", "name": "Human readable name", "architecture": {"output_modalities": ["text"]}}]})
    assert models[0]["name"] == "vendor/exact-api-id"
    assert models[0]["display_name"] == "Human readable name"
    assert models[0]["capabilities"] == ["chat"]


def test_discover_entered_endpoint_before_saving(client, monkeypatch):
    from osii.configuration import load_models_config
    before = load_models_config()
    calls = []
    monkeypatch.setattr("requests.get", lambda url, **kw: calls.append((url, kw)) or FakeResponse(
        payload={"data": [{"id": "published-model", "name": "Readable name"}]}))
    response = client.post("/api/admin/model-providers/discover", json={
        "type": "openai", "base_url": "https://new.test/v1", "api_key": "synthetic-key"})
    assert response.status_code == 200
    assert response.json()["models"][0] == {"id": "published-model", "name": "Readable name", "capabilities": []}
    assert response.json()["generation_tested"] is False
    assert load_models_config() == before
    assert calls[0][0] == "https://new.test/v1/models"


def test_default_ollama_provider_uses_small_us_models(client):
    payload = client.get("/api/admin/model-providers").json()
    embedder = next(item for item in payload["providers"] if item["id"] == "minilm")
    language = next(item for item in payload["providers"] if item["id"] == "base")
    assert embedder["enabled"] is True
    assert embedder["embedding_model"] == "all-minilm"
    assert language["chat_model"] == "llama3.2:1b"
    assert {item["model"] for item in payload["ollama_recommendations"]} == {"all-minilm", "llama3.2:1b"}


def test_corporate_preset_roundtrips_without_a_new_protocol(client):
    response = client.put("/api/admin/model-providers/corporate-endpoint", json={
        "type": "openai", "preset": "corporate",
        "base_url": "https://models.example.test/v1", "enabled": True,
        "chat_model": "chat-v1", "embedding_model": "embed-v1",
        "credential_env": "OSII_CORPORATE_API_KEY",
    })
    assert response.status_code == 200
    providers = client.get("/api/admin/model-providers").json()["providers"]
    saved = next(item for item in providers if item["id"] == "corporate-endpoint")
    assert saved["preset"] == "corporate"
    assert saved["type"] == "openai"
    assert saved["chat_model"] == "chat-v1"
    assert saved["embedding_model"] == "embed-v1"
    config = (Path(os.environ["OSII_CONFIG_DIR"]) / "models.toml").read_text()
    assert 'type = "openai-compatible"' in config
    assert 'preset = "corporate"' in config
    assert saved["credential_help"] == ""


def test_corporate_preset_rejects_incompatible_transport(client):
    response = client.put("/api/admin/model-providers/corporate-endpoint", json={
        "type": "ollama", "preset": "corporate", "base_url": "http://localhost:11434",
    })
    assert response.status_code == 422


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
    raw = (Path(os.environ["OSII_CONFIG_DIR"]) / "models.toml").read_text()
    assert "super-secret-value" not in raw
    assert "MY_CORPORATE_KEY" in raw
    assert 'model = "embed-v1"' in raw
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
    assert "saved-secret" not in (Path(os.environ["OSII_CONFIG_DIR"]) / "models.toml").read_text()

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
    assert provider["default_chat"] is True
    assert provider["default_embedding"] is True
    assert selected_processor("embedder") == "openai.embedder"
    assert selected_processor("synthesizer") == "openai.synthesizer"
    assert provider["credential_writable"] is False
    assert provider["credential_help"] == "OSII is using OPENAI_API_KEY from its startup environment."
    assert "alias-key" not in str(payload)

    blocked = client.put("/api/admin/model-providers/openai-compatible/credential",
                         json={"api_key": "replacement"})
    assert blocked.status_code == 409
    assert "OPENAI_API_KEY" in blocked.json()["detail"]
    assert "alias-key" not in blocked.text


def test_environment_suggestion_does_not_claim_to_override_saved_defaults(client, monkeypatch):
    client.get("/api/admin/model-providers")  # Save the initial local profile.
    monkeypatch.setenv("OPENAI_BASE_URL", "https://models.example.test/v1")
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "chat-v1")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "embed-v1")
    providers = client.get("/api/admin/model-providers").json()["providers"]
    suggestion = next(item for item in providers if item["id"] == "openai-compatible")
    assert suggestion["default_chat"] is False
    assert suggestion["default_embedding"] is False
    assert selected_processor("synthesizer") == "ollama.synthesizer"


def test_new_external_default_accepts_setup_key_when_environment_key_is_empty(client, monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://models.example.test/v1")
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "chat-v1")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.delenv("OPENAI_API_KEY_FILE", raising=False)
    monkeypatch.setenv("OSII_ALLOW_LOCAL_CONFIG_WRITES", "true")
    providers = client.get("/api/admin/model-providers").json()["providers"]
    provider = next(item for item in providers if item["id"] == "openai-compatible")
    assert provider["credential_writable"] is True
    saved = client.put("/api/admin/model-providers/openai-compatible/credential",
                       json={"api_key": "local-key"})
    assert saved.status_code == 200
    assert saved.json()["credential_source"] == "repo_env"
    assert "local-key" not in saved.text


def test_openai_environment_accepts_container_secret_file(client, monkeypatch, tmp_path):
    monkeypatch.setenv("OSII_ALLOW_LOCAL_CONFIG_WRITES", "false")
    secret = tmp_path / "openai_api_key"
    secret.write_text("mounted-secret\n", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY_FILE", str(secret))
    monkeypatch.setenv("OPENAI_BASE_URL", "https://models.example.test/v1")

    payload = client.get("/api/admin/model-providers").json()
    provider = next(item for item in payload["providers"] if item["id"] == "openai-compatible")

    assert provider["credential_present"] is True
    assert "mounted-secret" not in str(payload)
    assert provider["credential_source"] == "secret_file"
    assert provider["credential_writable"] is False
    assert "OPENAI_API_KEY_FILE" in provider["credential_help"]
    blocked = client.put("/api/admin/model-providers/openai-compatible/credential",
                         json={"api_key": "replacement"})
    assert blocked.status_code == 409
    assert "OPENAI_API_KEY_FILE" in blocked.json()["detail"]


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


def test_setup_rotates_startup_key_without_restart(client, monkeypatch, tmp_path):
    from osii.domain.env_credentials import resolve_env_value
    from osii.model_clients import _endpoint
    secrets = tmp_path / "secrets.env"
    monkeypatch.setenv("OSII_ENV_FILE", str(secrets))
    monkeypatch.setenv("OSII_ALLOW_LOCAL_CONFIG_WRITES", "true")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://litellm.example.test/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "bad-startup-key")
    monkeypatch.delenv("OPENAI_API_KEY_FILE", raising=False)
    providers = client.get("/api/admin/model-providers").json()["providers"]
    provider = next(item for item in providers if item["id"] == "openai-compatible")
    assert provider["credential_writable"] is True
    assert provider["credential_help"] == "OSII is using OPENAI_API_KEY from its startup environment."
    for replacement in ("replacement-one", "replacement-two"):
        response = client.put("/api/admin/model-providers/openai-compatible/credential",
                              json={"api_key": replacement})
        assert response.status_code == 200
        assert replacement not in response.text
        assert resolve_env_value("OPENAI_API_KEY") == (replacement, "repo_env")
        assert _endpoint("chat").api_key == replacement
        seen = []
        monkeypatch.setattr("requests.get", lambda *a, **kw: seen.append(kw["headers"]) or FakeResponse(payload={"data": []}))
        client.post("/api/admin/model-providers/openai-compatible/health")
        assert seen[0]["Authorization"] == f"Bearer {replacement}"
    assert __import__("os").environ["OPENAI_API_KEY"] == "bad-startup-key"


@pytest.mark.parametrize("key_file_exists", [True, False])
def test_optional_key_file_does_not_block_setup_or_local_replacement(client, monkeypatch, tmp_path, key_file_exists):
    from osii.configuration import default_models_config, load_models_config
    from osii.model_clients import _endpoint
    key_file = tmp_path / "provider-key"
    if key_file_exists:
        key_file.write_text("previous-file-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://corporate.test/v1")
    monkeypatch.setenv("OPENAI_API_KEY_FILE", str(key_file))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OSII_ALLOW_LOCAL_CONFIG_WRITES", "true")
    monkeypatch.setenv("OSII_ENV_FILE", str(tmp_path / "saved-secrets.env"))
    assert default_models_config()["models"]["openai-compatible"]["api_key_env"] == "OPENAI_API_KEY"
    assert load_models_config()
    response = client.get("/api/admin/model-providers")
    assert response.status_code == 200
    provider = next(p for p in response.json()["providers"] if p["id"] == "openai-compatible")
    assert provider["credential_writable"]
    saved = client.put("/api/admin/model-providers/openai-compatible/credential", json={"api_key": "replacement-from-setup"})
    assert saved.status_code == 200
    assert _endpoint("chat").api_key == "replacement-from-setup"
    assert key_file.exists() == key_file_exists


@pytest.mark.parametrize("capability,payload,ok", [
    ("embedding", {"data": [{"embedding": [0.1, 0.2]}]}, True),
    ("embedding", {"data": [{"embedding": []}]}, False),
    ("embedding", {"data": [{"embedding": [float("nan")]}]}, False),
    ("embedding", {"data": [{"embedding": ["text"]}]}, False),
    ("chat", {"choices": [{"message": {"content": "OK"}}]}, True),
    ("chat", {"choices": []}, False),
])
def test_explicit_model_probe_preserves_defaults(client, monkeypatch, capability, payload, ok):
    from osii.configuration import load_models_config
    client.put("/api/admin/model-providers/probe", json={"type": "openai", "base_url": "https://test.invalid/v1"})
    before = load_models_config()
    calls = []
    monkeypatch.setattr("requests.post", lambda url, **kw: calls.append((url, kw)) or FakeResponse(payload=payload))
    result = client.post("/api/admin/model-providers/probe/test-model", json={"model": "unknown-model", "capability": capability})
    assert result.status_code == 200
    assert result.json()["ok"] is ok
    assert len(calls) == 1
    assert calls[0][0].endswith("/embeddings" if capability == "embedding" else "/chat/completions")
    assert load_models_config() == before


def test_explicit_model_probe_validates_input(client):
    assert client.post("/api/admin/model-providers/absent/test-model", json={"model": "x", "capability": "chat"}).status_code == 404
    client.put("/api/admin/model-providers/probe", json={"type": "openai", "base_url": "https://test.invalid/v1"})
    assert client.post("/api/admin/model-providers/probe/test-model", json={"model": "", "capability": "chat"}).status_code == 422


def test_status_access_filter_retains_errors_and_actions():
    import logging
    from osii.processor_sdk.access_logs import StatusAccessFilter
    filter_ = StatusAccessFilter()
    def visible(method, path, status):
        return filter_.filter(logging.LogRecord("uvicorn.access", logging.INFO, "", 0, "%s %s %s %s %s", ("client", method, path, "1.1", status), None))
    assert not visible("GET", "/api/runs", 200)
    assert not visible("GET", "/health", 200)
    assert not visible("POST", "/api/admin/model-providers/discover", 200)
    assert visible("GET", "/api/runs", 500)
    assert visible("POST", "/api/admin/model-providers/discover", 401)
    assert visible("POST", "/api/intake", 200)
    assert visible("GET", "/api/objects", 200)


def test_connection_display_name_is_editable_without_changing_identity(client, monkeypatch):
    from osii.configuration import load_models_config
    monkeypatch.setenv("OPENAI_API_KEY", "test-name-secret")
    payload = {"type": "openai", "base_url": "https://openrouter.ai/api/v1", "chat_model": "chat", "embedding_model": "embedding", "enabled": True, "credential_env": "OPENAI_API_KEY"}
    first = client.put("/api/admin/model-providers/rename-test", json=payload).json()["provider"]
    before = load_models_config()
    result = client.put("/api/admin/model-providers/rename-test", json={**first, "display_name": "Corporate · Research"})
    assert result.status_code == 200
    providers = client.get("/api/admin/model-providers").json()["providers"]
    renamed = next(p for p in providers if p["id"] == "rename-test")
    assert renamed["display_name"] == "Corporate · Research"
    assert renamed["credential_present"]
    assert "test-name-secret" not in result.text
    after = load_models_config()
    assert before["defaults"] == after["defaults"]
    assert before["models"].keys() == after["models"].keys()
    assert after["models"]["rename-test-embedding"]["display_name"] == "Corporate · Research"
    assert renamed["chat_model"] == "chat" and renamed["embedding_model"] == "embedding"


def test_connection_display_name_length_is_bounded(client):
    response = client.put("/api/admin/model-providers/rename-test", json={"type": "openai", "base_url": "https://test.invalid/v1", "display_name": "x" * 201})
    assert response.status_code == 422
