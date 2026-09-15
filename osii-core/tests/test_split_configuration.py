from pathlib import Path

from osii.configuration import (
    configuration_status,
    load_models_config,
    load_tools_config,
    save_models_config,
)


class FakeDescriptorResponse:
    ok = True
    status_code = 200
    text = "ok"

    @staticmethod
    def raise_for_status():
        return None

    @staticmethod
    def json():
        return {
            "api_version": "v1",
            "name": "example.model-wiki",
            "version": "1.0.0",
            "display_name": "Example Model Wiki",
            "description": "Creates a wiki.",
            "kind": "enricher",
            "capabilities": {
                "media_types": [],
                "file_extensions": [],
                "scope_types": ["object", "collection"],
                "output_kinds": ["wiki_markdown"],
            },
            "config_schema": {},
            "model_requirements": {"chat": "required"},
        }


def test_register_running_processor_discovers_descriptor_and_writes_tools_yaml(
    client, monkeypatch
):
    monkeypatch.setattr(
        "osii.api.processor_admin_routes.requests.get",
        lambda *_, **__: FakeDescriptorResponse(),
    )

    response = client.post(
        "/api/admin/processors",
        json={"base_url": "http://127.0.0.1:8123", "model_connection": "base"},
    )

    assert response.status_code == 200
    processor = response.json()["processor"]
    assert processor["processor_id"] == "example.model-wiki"
    assert processor["model_access"]["bindings"] == {"chat": "base"}
    config = load_tools_config()
    assert config["profiles"]["development"]["tools"]["example.model-wiki"]["runtime"]["endpoint"] == "http://127.0.0.1:8123"


def test_invalid_yaml_retains_last_valid_generation_and_reports_line(monkeypatch):
    save_models_config({
        "version": 1,
        "models": {
            "base": {
                "type": "ollama-local",
                "base_url": "http://127.0.0.1:11434",
                "model": "llama3.2:1b",
                "capabilities": ["chat"],
            }
        },
        "defaults": {"chat": "base"},
    })
    path = Path(configuration_status()["files"]["models"])
    path.write_text("version: 1\nmodels: [\n", encoding="utf-8")

    retained = load_models_config()
    status = configuration_status()

    assert retained["models"]["base"]["model"] == "llama3.2:1b"
    assert "line 3" in status["errors"]["models"]
