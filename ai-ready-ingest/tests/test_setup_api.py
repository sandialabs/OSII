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
    assert payload["headline"] == "Ready for Intake — AI is optional"
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
