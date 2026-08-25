import json

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


def test_chat_falls_back_and_labels_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("OSII_ROOT", str(tmp_path))
    monkeypatch.setenv("CHAT_PROVIDER", "openai")
    monkeypatch.setenv("CHAT_PROVIDER_CHAIN", "openai,extractive")
    monkeypatch.setattr("app.main.retrieve_with_fallback", lambda **_: ("lexical", {"results": [{"file_id": "a", "filename": "a.txt", "snippet": "grounded evidence"}]}))

    def completion(**kwargs):
        if kwargs["provider"] == "openai":
            raise RuntimeError("provider down")
        return "extractive answer"

    monkeypatch.setattr("app.main.run_chat_completion", completion)
    response = TestClient(app).post("/api/chat", json={"query": "What?", "scope": {"scope_type": "root"}})
    assert response.status_code == 200
    assert response.json()["provider"] == "extractive"
    assert response.json()["fallback_used"] is True
    assert response.json()["retrieval_mode"] == "lexical"


def test_disabling_all_saved_providers_selects_extractive_chat(monkeypatch, tmp_path):
    provider_path = tmp_path / "state" / "model_providers.json"
    provider_path.parent.mkdir(parents=True)
    provider_path.write_text(json.dumps([]), encoding="utf-8")
    monkeypatch.setenv("OSII_ROOT", str(tmp_path))
    monkeypatch.setenv("CHAT_PROVIDER", "ollama")
    monkeypatch.setenv("CHAT_PROVIDER_CHAIN", "ollama,extractive")

    settings = get_settings()

    assert settings.chat_provider == "extractive"
    assert settings.chat_provider_chain == ("extractive",)


def test_saved_shirty_provider_uses_bundled_model_bridge(monkeypatch, tmp_path):
    provider_path = tmp_path / "state" / "model_providers.json"
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
    monkeypatch.setenv("OSII_ROOT", str(tmp_path))
    monkeypatch.setenv("OSII_MODEL_BRIDGE_URL", "http://127.0.0.1:18095")

    settings = get_settings()

    assert settings.chat_provider == "openai"
    assert settings.openai_compatible_base_url == "http://127.0.0.1:18095/shirty/v1"
    assert settings.openai_chat_model == "meta-llama/Llama-3.1-8B-Instruct"
