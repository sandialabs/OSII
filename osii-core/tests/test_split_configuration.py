from pathlib import Path
import json
import tomllib

from osii.configuration import (
    configuration_status,
    configured_tools,
    load_models_config,
    load_tools_config,
    save_models_config,
    save_tools_config,
)
from osii.domain.processing.extractor_selection import load_extractor_routes
from osii.domain.processor_settings import load_processor_settings


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


def test_register_running_processor_discovers_descriptor_and_writes_tools_toml(
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
    assert config["tools"]["example.model-wiki"]["runtime"]["endpoint"] == "http://127.0.0.1:8123"


def test_invalid_toml_retains_last_valid_generation_and_reports_line(monkeypatch):
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
    path.write_text("version = 1\n[models.base\n", encoding="utf-8")

    retained = load_models_config()
    status = configuration_status()

    assert retained["models"]["base"]["model"] == "llama3.2:1b"
    assert "line 2" in status["errors"]["models"]


def test_legacy_yaml_migrates_to_toml_without_overwriting_existing(tmp_path, monkeypatch):
    config_dir = tmp_path / "deployment"
    config_dir.mkdir()
    monkeypatch.setenv("OSII_CONFIG_DIR", str(config_dir))
    (config_dir / "models.yml").write_text(
        "version: 1\nmodels:\n  top:\n    type: openai-compatible\n    base_url: https://models.example.test/v1\n    api_key_env: OPENAI_API_KEY\n    model: quality-model\n    capabilities: [chat]\ndefaults: {chat: top}\n",
        encoding="utf-8",
    )
    (config_dir / "tools.yml").write_text(
        "version: 1\nprofiles:\n  development:\n    tools:\n      wiki:\n        enabled: true\n        processor_id: toolbox.readable-wiki\n        unused: null\n        runtime: {mode: external, endpoint: 'http://127.0.0.1:8099'}\n",
        encoding="utf-8",
    )
    assert load_models_config()["models"]["top"]["model"] == "quality-model"
    assert load_tools_config()["tools"]["wiki"]["processor_id"] == "toolbox.readable-wiki"
    assert tomllib.loads((config_dir / "models.toml").read_text())["defaults"]["chat"] == "top"
    assert tomllib.loads((config_dir / "tools.toml").read_text())["tools"]["wiki"]["enabled"]
    assert "unused" not in tomllib.loads((config_dir / "tools.toml").read_text())["tools"]["wiki"]
    (config_dir / "models.yml").write_text("models: {}\n", encoding="utf-8")
    assert load_models_config()["models"]["top"]["model"] == "quality-model"


def test_profile_routes_and_processor_settings_are_toml_not_sidecar(tmp_path, monkeypatch):
    config_dir = tmp_path / "deployment"
    monkeypatch.setenv("OSII_CONFIG_DIR", str(config_dir))
    monkeypatch.delenv("OSII_EXTRACTOR_ROUTES_PATH", raising=False)
    osii_root = tmp_path / "data" / ".osii"
    (osii_root / "state").mkdir(parents=True)
    (osii_root / "state" / "processor_settings.json").write_text(
        json.dumps({"toolbox.readable-wiki": {"temperature": 0.2}}), encoding="utf-8",
    )
    config = load_tools_config(osii_root)
    assert config["processor_settings"]["toolbox.readable-wiki"]["temperature"] == 0.2
    assert load_processor_settings(osii_root)["toolbox.readable-wiki"]["temperature"] == 0.2
    assert load_extractor_routes()[0]["extractor"] == "local.native-text"
    config.setdefault("routes", {})["extractor"] = [
        {"name": "custom", "extractor": "toolbox.tesseract-opencv", "extensions": [".pdf"]}
    ]
    save_tools_config(config)
    assert load_extractor_routes()[0]["extractor"] == "toolbox.tesseract-opencv"
    assert "routes" in tomllib.loads((config_dir / "tools.toml").read_text())


def test_unselected_toolbox_processors_are_not_registered_in_direct_compose(monkeypatch):
    monkeypatch.setenv("OSII_ACTIVE_PROFILE", "containers")
    assert configured_tools() == {}
    monkeypatch.setenv("OSII_ACTIVE_PROFILE", "development")
    assert "readable-llm-wiki" in configured_tools()


def test_custom_old_route_file_is_imported_without_writing_to_source(tmp_path, monkeypatch):
    source = tmp_path / "read-only-source"
    source.mkdir()
    original = source / "example.pdf"
    original.write_bytes(b"original")
    old_routes = tmp_path / "old-routes.toml"
    old_routes.write_text(
        '[[routes]]\nname = "special-pdf"\nextractor = "toolbox.tesseract-opencv"\nextensions = [".pdf"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("OSII_CONFIG_DIR", str(tmp_path / "profile" / "deployment"))
    monkeypatch.setenv("OSII_EXTRACTOR_ROUTES_PATH", str(old_routes))
    assert load_tools_config()["routes"]["extractor"][0]["name"] == "special-pdf"
    assert original.read_bytes() == b"original"
    assert sorted(path.name for path in source.iterdir()) == ["example.pdf"]
