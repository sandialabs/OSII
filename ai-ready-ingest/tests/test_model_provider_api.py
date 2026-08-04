def test_model_provider_configuration_never_persists_secret(client, temp_osii_root, monkeypatch):
    monkeypatch.setenv("MY_CORPORATE_KEY", "super-secret-value")
    response = client.put("/api/admin/model-providers/corporate", json={
        "id": "corporate",
        "type": "shirty",
        "base_url": "https://models.example.test/v1",
        "enabled": True,
        "priority": 10,
        "embedding_model": "embed-v1",
        "synthesis_model": "chat-v1",
        "chat_model": "chat-v1",
        "credential_env": "MY_CORPORATE_KEY",
    })
    assert response.status_code == 200
    assert response.json()["provider"]["credential_present"] is True
    raw = (temp_osii_root / "state" / "model_providers.json").read_text()
    assert "super-secret-value" not in raw
    assert "MY_CORPORATE_KEY" in raw
