import pytest
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


def test_discovery_previews_unsaved_endpoint_without_reusing_another_key(client, app, monkeypatch):
    import requests
    from osii.server.model_connections import ModelConnections
    manager = ModelConnections(app.state.store, app.state.settings)
    manager.save("chat", {"base_url": "https://old.test/v1", "api_key": "old-synthetic-key", "model": "old-model"})
    before = app.state.store.setting("model_endpoints", {})
    calls = []
    class Response:
        ok, status_code = True, 200
        def json(self): return {"data": [{"id": "exact-model-name", "name": "Friendly model"}]}
    monkeypatch.setattr(requests, "get", lambda url, **kw: calls.append((url, kw)) or Response())
    login(client, "reader")
    assert client.post("/api/admin/models/endpoints/chat/discover", json={"base_url": "https://new.test/v1"}).status_code == 403
    login(client)
    result = client.post("/api/admin/models/endpoints/chat/discover", json={"base_url": "https://new.test/v1"})
    assert result.status_code == 200 and result.json()["saved"] is False
    assert result.json()["models"][0]["id"] == "exact-model-name"
    assert "Authorization" not in calls[0][1]["headers"]
    assert app.state.store.setting("model_endpoints", {}) == before
    assert app.state.store.configuration()["chat_model"] == "old-model"


def test_save_connection_keeps_endpoint_and_selected_model_together(client, app):
    login(client)
    result = client.put("/api/admin/models/endpoints/chat", json={"base_url": "https://chat.test/v1",
        "model": "vendor/published-model", "model_name": "Friendly model", "api_key": "synthetic-private-key"})
    assert result.status_code == 200
    public = client.get("/api/admin/models").json()
    assert public["chat_model"] == "vendor/published-model"
    assert public["endpoints"]["chat"]["model_name"] == "Friendly model"
    assert "synthetic-private-key" not in str(public)
    # A failed second setting write must roll back both endpoint and selection.
    from sqlalchemy import event
    import pytest
    def fail_models_write(conn, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO settings") and parameters.get("id") == "models":
            raise RuntimeError("synthetic write failure")
    event.listen(app.state.store.engine, "before_cursor_execute", fail_models_write)
    try:
        with pytest.raises(RuntimeError):
            app.state.store.save_model_connection("chat", {"base_url": "https://changed.test/v1", "api_key": "new-synthetic-key"}, model="different")
    finally:
        event.remove(app.state.store.engine, "before_cursor_execute", fail_models_write)
    assert app.state.store.setting("model_endpoints", {})["chat"]["base_url"] == "https://chat.test/v1"
    assert app.state.store.configuration()["chat_model"] == "vendor/published-model"


def test_flat_catalog_includes_nested_files_without_requesting_folder_mode(client, app):
    document(app.state.store, app.state.settings.source_root, name="nested/report.txt")
    login(client, "reader")
    assert client.get("/api/catalog/files").json()["total"] == 1
    assert client.get("/api/catalog/files?direct=true").json()["total"] == 0


def test_sample_test_invokes_only_the_chosen_connection(client, app, monkeypatch):
    app.state.store.save_configuration({"chat_model": "chat", "embedding_model": "embedding"})
    monkeypatch.setattr(Provider, "embed", lambda *a: (_ for _ in ()).throw(AssertionError("Unexpected embedding call")))
    login(client)
    result = client.post("/api/admin/models/test?only=chat")
    assert result.status_code == 200 and result.json() == {"chat": {"configured": True, "ok": True}}


def test_file_cards_report_saved_products_without_loading_corpus_payloads(client, app, monkeypatch):
    from conftest import document, login
    from sqlalchemy import insert, update
    from osii.persistence.postgres import artifacts, documents
    store = app.state.store
    doc = document(store, app.state.settings.source_root)
    with store.transaction() as c:
        c.execute(insert(artifacts), [
            dict(id='card-synthesis',file_id=doc['file_id'],kind='synthesis',payload={'not':'read by catalog'}),
            dict(id='card-enrichment',file_id=doc['file_id'],kind='enrichment',payload={'not':'read by catalog'}),
        ])
    monkeypatch.setattr(store, 'snapshot', lambda: pytest.fail('File cards must not load chunk vectors'))
    login(client, 'reader')
    response = client.get('/api/catalog/files')
    assert response.status_code == 200
    item = response.json()['items'][0]
    assert item['has_text'] and item['has_synthesis'] and item['has_enrichments']
    assert item['updated_at']
    from datetime import datetime, timezone
    expected=datetime.fromtimestamp((app.state.settings.source_root/'report.txt').stat().st_mtime,timezone.utc).isoformat()
    assert item['modified_at']==expected
    assert not {'text','embedding','metadata','payload'} & item.keys()
    with store.transaction() as c:
        c.execute(update(documents).where(documents.c.file_id==doc['file_id']).values(text='   '))
    assert not client.get('/api/catalog/files').json()['items'][0]['has_text']


def test_setup_statistics_check_current_model_coverage_and_remain_admin_only(client, app, monkeypatch):
    from conftest import document, login, Provider
    from sqlalchemy import update, insert
    from osii.persistence.postgres import chunks, datasets
    store = app.state.store
    store.save_configuration({'embedding_model':'test-embeddings'})
    first = document(store, app.state.settings.source_root, name='first.txt')
    second = document(store, app.state.settings.source_root, name='second.txt',content='A different source document.')
    monkeypatch.setattr(Provider,'embed',lambda *_: pytest.fail('Readiness must not invoke models'))
    monkeypatch.setattr(Provider,'chat',lambda *_: pytest.fail('Readiness must not invoke models'))
    assert client.get('/api/admin/source').status_code == 401
    for user in ('reader','curator'):
        login(client,user)
        assert client.get('/api/admin/source').status_code == 403
    login(client,'admin')
    stats=client.get('/api/admin/source').json()['statistics']
    assert stats['documents']==stats['text_documents']==stats['indexed_documents']==2
    with store.transaction() as c:
        c.execute(insert(chunks).values(chunk_id='stale-extra',file_id=first['file_id'],text='old',char_start=0,char_end=3,source_origin={},embedding=[1,0],embedding_model='old-model'))
        c.execute(update(chunks).where(chunks.c.file_id==second['file_id']).values(embedding=[]))
        c.execute(update(datasets).where(datasets.c.id=='shared').values(revision=datasets.c.revision+1))
    assert client.get('/api/admin/source').json()['statistics']['indexed_documents']==0
    with store.transaction() as c:
        c.execute(update(chunks).where(chunks.c.file_id==second['file_id']).values(embedding=None))
    assert store.statistics()['indexed_documents']==0
    store.save_configuration({'embedding_model':''})
    assert store.statistics()['indexed_documents']==0


def test_readiness_cache_tracks_real_commits_and_selected_model(app, monkeypatch):
    store = app.state.store
    store.save_configuration({'embedding_model':'test-embeddings'})
    first = document(store, app.state.settings.source_root)
    calculate = store._calculate_statistics
    calls = []
    def spy(connection, model):
        calls.append(model)
        return calculate(connection, model)
    monkeypatch.setattr(store, '_calculate_statistics', spy)
    original = store.statistics(use_cache=True)
    assert store.statistics(use_cache=True) == original and len(calls) == 1
    # A new API process can reuse the same derived PostgreSQL record.
    from osii.persistence.postgres import PostgresStore
    fresh = PostgresStore(store.engine.url.render_as_string(hide_password=False))
    monkeypatch.setattr(fresh, '_calculate_statistics', lambda *_: pytest.fail('A valid persisted cache must skip vector aggregates'))
    try:
        assert fresh.statistics(use_cache=True) == original
    finally:
        fresh.engine.dispose()
    rows=store.document_chunks(first['file_id'])
    store.replace_embeddings(first['file_id'], [{**row,'embedding':None} for row in rows], 'test-embeddings')
    assert store.statistics(use_cache=True)['indexed_documents'] == 0 and len(calls) == 2
    # Changing the selected model invalidates counts even without a new dataset revision.
    store.save_configuration({'embedding_model':'different'})
    assert store.statistics(use_cache=True)['indexed_documents'] == 0 and len(calls) == 3
    store.save_setting('readiness_statistics', {'identity':store.setting('readiness_statistics', {})['identity'],'result':{'documents':'corrupt'}})
    assert store.statistics(use_cache=True)['documents'] == 1 and len(calls) == 4
    document(store, app.state.settings.source_root, name='new.txt',content='A new source document')
    assert store.statistics(use_cache=True)['documents'] == 2 and len(calls) == 5


def test_simultaneous_readiness_requests_share_one_calculation(app, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    store = app.state.store
    document(store, app.state.settings.source_root)
    calculate = store._calculate_statistics
    calls = []
    def spy(connection, model):
        calls.append(model)
        return calculate(connection, model)
    monkeypatch.setattr(store, '_calculate_statistics', spy)
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(lambda _: store.statistics(use_cache=True), range(3)))
    assert results[0] == results[1] == results[2]
    assert len(calls) == 1
