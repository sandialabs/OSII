from osii.domain.processor_settings import merged_processor_settings


def test_processor_settings_are_saved_and_merged(client, temp_osii_root):
    response = client.put(
        "/api/admin/processor-settings/ollama.synthesizer",
        json={
            "config": {
                "instructions": "Use a demonstration-friendly structure.",
                "temperature": 0.1,
            }
        },
    )

    assert response.status_code == 200
    assert (
        client.get("/api/admin/processor-settings").json()["settings"][
            "ollama.synthesizer"
        ]["temperature"]
        == 0.1
    )
    assert merged_processor_settings(
        temp_osii_root,
        "ollama.synthesizer",
        {"temperature": 0.4},
    ) == {
        "instructions": "Use a demonstration-friendly structure.",
        "temperature": 0.4,
    }


def test_processor_settings_reject_non_object_config(client):
    response = client.put(
        "/api/admin/processor-settings/local.native-text",
        json={"config": "not-an-object"},
    )

    assert response.status_code == 422


def test_processor_settings_reject_toml_incompatible_null(client):
    response = client.put(
        "/api/admin/processor-settings/local.native-text",
        json={"config": {"temperature": None}},
    )
    assert response.status_code == 422


def test_manifest_startup_settings_validate_persist_and_report_environment_overrides(client, monkeypatch, startup_module):
    from osii.configuration import load_tools_config
    monkeypatch.setenv('EXAMPLE_CACHE_ENABLED', 'true')
    modules = client.get('/api/admin/processor-settings/startup').json()
    example = next(item for item in modules['processors'] if item['id'] == 'example-cache')
    assert example['schema']['properties']['EXAMPLE_CACHE_PORT']['default'] == 9998
    assert example['environment_overrides'] == ['EXAMPLE_CACHE_ENABLED']
    from pathlib import Path
    assert Path(modules['path']).name == 'processors.toml'
    endpoint = '/api/admin/processor-settings/startup/example-cache'
    config = {'EXAMPLE_CACHE_ENABLED': False, 'EXAMPLE_CACHE_PORT': 19998}
    saved = client.put(endpoint, json={'config': config})
    assert saved.status_code == 200 and saved.json()['restart_required']
    assert load_tools_config()['processor_startup']['example-cache'] == config
    for bad in ({'EXAMPLE_CACHE_ENABLED': 'false'}, {'EXAMPLE_CACHE_PORT': 0}, {'DATABASE_URL': 'not-a-module-setting'}):
        assert client.put(endpoint, json={'config': bad}).status_code == 422
        assert load_tools_config()['processor_startup']['example-cache'] == config
    assert client.put('/api/admin/processor-settings/startup/missing', json={'config': {}}).status_code == 404
