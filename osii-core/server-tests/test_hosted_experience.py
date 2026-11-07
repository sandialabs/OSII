from datetime import timedelta
from sqlalchemy import update
from conftest import document, login, Provider
from osii.persistence.postgres import sessions, now


def test_remembered_session_survives_inactivity_and_logout_revokes(client, app):
    response = client.post("/api/auth/login", json={"username": "reader", "password": "sufficiently-long-test-password", "remember": True})
    assert response.status_code == 200
    cookies = response.headers.get_list("set-cookie")
    assert all("Max-Age=1209600" in header for header in cookies)
    assert "HttpOnly" in next(h for h in cookies if h.startswith("osii_session="))
    with app.state.store.transaction() as c:
        c.execute(update(sessions).values(last_seen=now() - timedelta(days=2)))
    assert client.get("/api/auth/me").status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_ordinary_session_still_expires_after_short_idle(client, app):
    login(client, "reader")
    with app.state.store.transaction() as c:
        c.execute(update(sessions).values(last_seen=now() - timedelta(hours=1)))
    assert client.get("/api/auth/me").status_code == 401


def test_remembered_session_has_absolute_and_idle_limits(client, app):
    def sign_in():
        assert client.post("/api/auth/login", json={"username": "reader", "password": "sufficiently-long-test-password", "remember": True}).status_code == 200
    sign_in()
    with app.state.store.transaction() as c:
        c.execute(update(sessions).values(last_seen=now() - timedelta(days=8)))
    assert client.get("/api/auth/me").status_code == 401
    sign_in()
    with app.state.store.transaction() as c:
        c.execute(update(sessions).values(expires_at=now() - timedelta(seconds=1)))
    assert client.get("/api/auth/me").status_code == 401


def test_endpoint_edits_are_admin_only_and_keys_write_only(client, app):
    login(client, "reader")
    assert client.put("/api/admin/models/endpoints/chat", json={"base_url": "https://chat.test/v1"}).status_code == 403
    assert client.delete("/api/admin/models/endpoints/chat").status_code == 403
    login(client)
    result = client.put("/api/admin/models/endpoints/chat", json={"base_url": "https://chat.test/v1", "api_key": "synthetic-private-key"})
    assert result.status_code == 200
    assert "synthetic-private-key" not in result.text
    assert result.json()["credential_present"]
    assert "synthetic-private-key" not in client.get("/api/admin/models").text
    # URL change with no new key must not forward the old endpoint's credential.
    result = client.put("/api/admin/models/endpoints/chat", json={"base_url": "https://different.test/v1"})
    assert not result.json()["credential_present"]
    assert client.delete("/api/admin/models/endpoints/chat").json()["managed_by"] == "deployment"


def test_validation_never_echoes_write_only_keys(client):
    login(client)
    secret = "synthetic-private-key"
    response = client.put("/api/admin/models/endpoints/chat", json={"api_key": secret})
    assert response.status_code == 422 and secret not in response.text


def test_keyword_search_never_calls_embedding_and_folder_browse_is_direct(client, app, monkeypatch):
    first = document(app.state.store, app.state.settings.source_root, name="nested/deeper/report.txt")
    root = document(app.state.store, app.state.settings.source_root, name="root.txt", content="A separate neutron calibration report.")
    app.state.store.save_configuration({"chat_model": "", "embedding_model": "unavailable"})
    monkeypatch.setattr(Provider, "embed", lambda *a: (_ for _ in ()).throw(AssertionError("Keyword search invoked embeddings")))
    login(client, "reader")
    result = client.post("/api/search", json={"query": "neutron", "mode": "lexical"})
    assert result.status_code == 200 and len(result.json()["results"]) == 2
    assert {d["file_id"] for d in client.get("/api/catalog/files?direct=true").json()["items"]} == {root["file_id"]}
    assert "nested" in {f["path"] for f in client.get("/api/catalog/folders").json()["items"]}
    files = client.get("/api/catalog/files?direct=true&folder_id=nested/deeper").json()["items"]
    assert [d["file_id"] for d in files] == [first["file_id"]]


def test_failed_embeddings_preserve_text_for_keyword_search(store, tmp_path, monkeypatch):
    from osii.model_provider import ProviderError
    store.save_configuration({"chat_model": "", "embedding_model": "offline-model"})
    monkeypatch.setattr(Provider, "embed", lambda *a: (_ for _ in ()).throw(ProviderError("Embedding endpoint is unavailable")))
    doc = document(store, tmp_path)
    assert doc["text"] and doc["metadata"]["embedding_warning"]
    assert not any(row["embedding"] for row in store.snapshot()[2])


def test_endpoint_changes_wait_for_processing(client, app):
    login(client)
    app.state.store.enqueue("ingest", {})
    assert client.put("/api/admin/models/endpoints/chat", json={"base_url": "https://chat.test/v1"}).status_code == 409


def test_saved_endpoints_apply_to_existing_provider_without_restart(app, monkeypatch):
    import requests
    from osii.server.model_connections import ModelConnections, ConfiguredModelProvider
    manager = ModelConnections(app.state.store, app.state.settings)
    provider = ConfiguredModelProvider(manager)
    calls = []
    class Response:
        ok, status_code = True, 200
        def __init__(self, data): self.data = data
        def json(self): return self.data
    def invoke(method, url, **kwargs):
        calls.append((url, kwargs["headers"].get("Authorization")))
        return Response({"data": [{"index": 0, "embedding": [1, 0]}]} if url.endswith("/embeddings")
                        else {"choices": [{"message": {"content": "synthetic answer"}}]})
    monkeypatch.setattr(requests, "request", invoke)
    manager.save("chat", {"base_url": "https://chat.test/v1", "api_key": "synthetic-chat"})
    manager.save("embedding", {"base_url": "https://embedding.test/v1", "api_key": "synthetic-embedding"})
    provider.chat("chat-model", [])
    provider.embed("embedding-model", ["text"])
    assert calls == [("https://chat.test/v1/chat/completions", "Bearer synthetic-chat"),
                     ("https://embedding.test/v1/embeddings", "Bearer synthetic-embedding")]
