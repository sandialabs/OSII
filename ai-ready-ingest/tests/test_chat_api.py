import json

from osii.api.chat_routes import get_chat_settings


def test_chat_api_falls_back_to_extractive(monkeypatch, client, temp_osii_root):
    monkeypatch.setenv("CHAT_PROVIDER", "openai")
    monkeypatch.setenv("CHAT_PROVIDER_CHAIN", "openai,extractive")
    monkeypatch.setattr(
        "osii.api.chat_routes.dashboard_search",
        lambda *_args, **_kwargs: (
            "lexical",
            [{"file_id": "a", "filename": "a.txt", "snippet": "grounded evidence"}],
        ),
    )

    def completion(**kwargs):
        if kwargs["provider"] == "openai":
            raise RuntimeError("provider down")
        return "extractive answer"

    monkeypatch.setattr("osii.api.chat_routes.run_chat_completion", completion)

    response = client.post(
        "/api/chat",
        json={"query": "What?", "scope": {"scope_type": "root"}},
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "extractive"
    assert response.json()["fallback_used"] is True
    assert response.json()["retrieval_mode"] == "lexical"


def test_saved_shirty_provider_uses_bundled_model_bridge(monkeypatch, temp_osii_root):
    provider_path = temp_osii_root / "state" / "model_providers.json"
    provider_path.parent.mkdir(parents=True)
    provider_path.write_text(
        json.dumps(
            [
                {
                    "id": "corporate",
                    "type": "shirty",
                    "base_url": "https://shirty.sandia.gov/api/v1",
                    "enabled": True,
                    "priority": 10,
                    "chat_model": "meta-llama/Llama-3.1-8B-Instruct",
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("OSII_MODEL_BRIDGE_URL", "http://127.0.0.1:18095")

    settings = get_chat_settings(temp_osii_root)

    assert settings.chat_provider_chain == ("shirty", "extractive")
    assert settings.openai_compatible_base_url == "http://127.0.0.1:18095/shirty/v1"
    assert settings.openai_chat_model == "meta-llama/Llama-3.1-8B-Instruct"
    assert settings.openai_compatible_api_key == ""


def test_chat_health(client):
    response = client.get("/api/chat/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "osii-core-chat"}


def test_chat_api_handles_a_new_empty_catalog(monkeypatch, client):
    monkeypatch.setenv("CHAT_PROVIDER", "extractive")
    monkeypatch.setattr(
        "osii.api.chat_routes.dashboard_search",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("No valid chunk rows found in chunk manifest: /data/.osii/embeddings/chunks/chunks.jsonl")
        ),
    )

    response = client.post(
        "/api/chat",
        json={"query": "What is indexed?", "scope": {"scope_type": "root"}},
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "extractive"
    assert response.json()["retrieval_mode"] == "empty"
    assert "could not find grounded text" in response.json()["answer"]
