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
