from osii.configuration import load_models_config, save_models_config
from osii.domain.processing import quick_intake


def test_distinct_language_defaults_are_verified_without_rewriting(client, temp_osii_root, monkeypatch):
    settings = {
        "version": 1,
        "defaults": {"chat": "chat", "synthesis": "writer"},
        "models": {
            alias: {"type": "openai-compatible", "base_url": "http://example.invalid/v1",
                    "model": alias, "enabled": True, "capabilities": [role], "api_key_env": "TEST_MODEL_KEY"}
            for alias, role in [("chat", "chat"), ("writer", "synthesis")]
        },
    }
    monkeypatch.setenv("TEST_MODEL_KEY", "synthetic-credential-old")
    save_models_config(settings)
    calls = []

    def probe(url, protocol, key, model, capability):
        calls.append((model, capability))
        return {"ok": True}

    monkeypatch.setattr(quick_intake, "probe_model", probe)
    assert client.get("/api/intake/quick-start").json()["language"]["state"] == "needs_test"
    assert calls == []
    assert client.post("/api/intake/quick-start/check/language").json()["language"]["state"] == "ready"
    assert calls == [("chat", "chat"), ("writer", "chat")]
    assert load_models_config(temp_osii_root)["defaults"] == settings["defaults"]
    monkeypatch.setenv("TEST_MODEL_KEY", "synthetic-credential-new")
    assert client.get("/api/intake/quick-start").json()["language"]["state"] == "needs_test"
    assert "synthetic-credential" not in (temp_osii_root / "state/quick-intake.json").read_text()


def test_bundled_embeddings_verify_automatically_and_defer_to_saved_config(client, temp_osii_root, monkeypatch):
    from osii.domain.processing import capability_readiness

    monkeypatch.setenv("OSII_DEFAULT_EMBEDDER", "bundled.embeddinggemma")
    monkeypatch.setenv("EMBEDDING_MODEL", "embeddinggemma")
    monkeypatch.setenv("OSII_BUNDLED_EMBEDDER_URL", "http://127.0.0.1:9031")
    save_models_config({"version": 1, "defaults": {}, "models": {}})
    monkeypatch.setattr(capability_readiness, "embedding_readiness", lambda root: {"available": True})
    quick_intake.check_bundled_at_startup(temp_osii_root)

    state = client.get("/api/intake/quick-start").json()
    assert state["embedding"] == {"state": "ready", "models": ["embeddinggemma"], "bundled": True, "detail": None}
    assert state["language"]["state"] == "needs_connection" and not state["ready"]

    save_models_config({
        "version": 1, "defaults": {"embedding": "custom"},
        "models": {"custom": {"type": "openai-compatible", "base_url": "http://example.invalid/v1",
                              "model": "custom-vectors", "enabled": True, "capabilities": ["embedding"]}},
    })
    state = client.get("/api/intake/quick-start").json()
    assert state["embedding"]["state"] == "needs_test" and not state["embedding"]["bundled"]
