def _offline_readiness():
    return {
        "defaults": {
            "extractor": "local.native-text",
            "synthesizer": "local.extractive-preview",
            "embedder": "local.hashing",
            "enricher": "local.stats-keywords",
        },
        "extractors": [{
            "id": "local.native-text", "display_name": "Python document extractor",
            "available": True, "description": "Reads stored text.",
        }],
        "synthesizers": [{
            "id": "local.extractive-preview", "display_name": "Source excerpt preview — no AI",
            "available": True, "description": "Copies cited excerpts.",
        }],
        "embedders": [{
            "id": "local.hashing", "display_name": "Lexical hashing",
            "available": True, "description": "Compatibility vectors.",
        }],
        "enrichers": [{
            "id": "local.stats-keywords", "display_name": "Statistics and keywords",
            "available": True, "description": "Local knowledge products.",
        }],
        "external": [],
        "semantic_indexes": [],
    }


def test_setup_summary_treats_offline_baseline_as_ready(client, monkeypatch):
    monkeypatch.setattr(
        "osii.api.setup_routes.intake_capability_readiness",
        lambda _: _offline_readiness(),
    )
    monkeypatch.setattr("osii.api.setup_routes._services", lambda: (False, []))

    response = client.get("/api/admin/setup")

    assert response.status_code == 200
    payload = response.json()
    assert payload["overall_status"] == "ready_optional"
    assert payload["headline"] == "Complete model setup for semantic search and AI chat"
    assert payload["extraction_ready"] is True
    assert payload["ai_ready"] is False
    assert payload["methods"]["synthesizer"]["display_name"] == "Source excerpt preview — no AI"


def test_service_control_proxy_uses_private_launcher_token(client, monkeypatch):
    monkeypatch.setenv("OSII_SERVICE_SUPERVISOR_URL", "http://127.0.0.1:8510")
    monkeypatch.setenv("OSII_SERVICE_SUPERVISOR_TOKEN", "private-token")
    seen = {}

    class Response:
        ok = True
        status_code = 200

        @staticmethod
        def json():
            return {"services": []}

    def fake_request(method, url, **kwargs):
        seen.update({"method": method, "url": url, **kwargs})
        return Response()

    monkeypatch.setattr("osii.api.setup_routes.requests.request", fake_request)
    response = client.get("/api/admin/services")

    assert response.status_code == 200
    assert seen["url"] == "http://127.0.0.1:8510/services"
    assert seen["headers"] == {"Authorization": "Bearer private-token"}


def test_setup_ai_readiness_requires_both_selected_embedding_and_language_models(client, monkeypatch):
    readiness = _offline_readiness()
    readiness["defaults"]["embedder"] = "openai.embedder"
    readiness["embedders"].append({"id": "openai.embedder", "available": True})
    readiness["language_model"] = {"available": False}
    monkeypatch.setattr("osii.api.setup_routes.intake_capability_readiness", lambda _: readiness)
    monkeypatch.setattr("osii.api.setup_routes._services", lambda: (False, []))
    assert client.get("/api/admin/setup").json()["ai_ready"] is False
    readiness["language_model"]["available"] = True
    assert client.get("/api/admin/setup").json()["ai_ready"] is True
    readiness["embedders"][-1]["available"] = False
    assert client.get("/api/admin/setup").json()["ai_ready"] is False
    readiness["defaults"]["embedder"] = "local.hashing"
    assert client.get("/api/admin/setup").json()["ai_ready"] is False


def test_language_readiness_lists_selected_model_without_generating(temp_osii_root, monkeypatch):
    from osii.configuration import save_models_config
    from osii.domain.processing.capability_readiness import language_model_readiness

    save_models_config({"defaults": {"chat": "corporate"}, "models": {"corporate": {
        "type": "openai-compatible", "enabled": True, "capabilities": ["chat"],
        "base_url": "https://endpoint.example.test/v1", "model": "approved-chat",
        "api_key_env": "TEST_CHAT_CREDENTIAL",
    }}})
    monkeypatch.setenv("TEST_CHAT_CREDENTIAL", "test-only-key")
    seen = {}
    payload = {"data": [{"id": "approved-chat"}]}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return payload

    def get(url, **kwargs):
        seen.update({"url": url, **kwargs})
        return Response()

    monkeypatch.setattr("osii.domain.processing.capability_readiness.requests.get", get)
    result = language_model_readiness(temp_osii_root)
    assert result["available"] is True
    assert "Generation has not been tested" in result["detail"]
    assert seen["url"] == "https://endpoint.example.test/v1/models"
    assert seen["headers"] == {"Authorization": "Bearer test-only-key"}
    assert "test-only-key" not in str(result)
    payload["data"] = [{"id": "another-chat"}]
    assert language_model_readiness(temp_osii_root)["available"] is False


def test_language_readiness_accepts_ollama_latest_name_and_handles_unreachable_endpoint(temp_osii_root, monkeypatch):
    import requests
    from osii.configuration import save_models_config
    from osii.domain.processing.capability_readiness import language_model_readiness

    save_models_config({"defaults": {"chat": "local"}, "models": {"local": {
        "type": "ollama-local", "enabled": True, "capabilities": ["chat"],
        "base_url": "http://localhost:11434", "model": "approved-chat",
    }}})

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"models": [{"name": "approved-chat:latest"}]}

    monkeypatch.setattr("osii.domain.processing.capability_readiness.requests.get", lambda *_, **__: Response())
    assert language_model_readiness(temp_osii_root)["available"] is True

    def offline(*_, **__):
        raise requests.ConnectionError("Not reachable")

    monkeypatch.setattr("osii.domain.processing.capability_readiness.requests.get", offline)
    result = language_model_readiness(temp_osii_root)
    assert result["available"] is False
    assert "Not reachable" in result["detail"]
