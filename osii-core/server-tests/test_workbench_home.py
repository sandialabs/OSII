from sqlalchemy import insert, update, event
from conftest import login
from osii.persistence.postgres import documents, chunks, datasets, now


def test_home_is_safe_for_readers_and_setup_dismissal_is_admin_only(
    client, app, monkeypatch
):
    assert client.get("/api/workbench/home").status_code == 401
    login(client, "reader")
    result = client.get("/api/workbench/home")
    assert result.status_code == 200
    assert result.json()["setup"] == {"visible": False}
    assert client.post("/api/admin/setup/dismiss", json={}).status_code == 403
    login(client, "curator")
    assert not client.get("/api/workbench/home").json()["setup"]["visible"]
    assert client.post("/api/admin/setup/dismiss", json={}).status_code == 403
    login(client)
    assert client.get("/api/workbench/home").json()["setup"]["visible"]
    csrf = client.headers.pop("X-CSRF-Token")
    assert client.post("/api/admin/setup/dismiss", json={}).status_code == 403
    client.headers["X-CSRF-Token"] = csrf
    assert client.post("/api/admin/setup/dismiss", json={}).status_code == 200
    assert not client.get("/api/workbench/home").json()["setup"]["visible"]
    assert app.state.store.setting("home_setup", {}) == {"dismissed": True}


def test_home_uses_aggregates_and_reports_partial_indexing(client, app, monkeypatch):
    store = app.state.store

    def forbidden(*args, **kwargs):
        raise AssertionError("Home invoked a model or materialized the corpus")

    monkeypatch.setattr(store, "snapshot", forbidden)
    with store.transaction() as c:
        for i in range(3):
            c.execute(
                insert(documents).values(
                    file_id=str(i),
                    source_relpath=f"{i}.pdf",
                    filename=f"{i}.pdf",
                    media_type="application/pdf",
                    active=True,
                    sha256=str(i),
                    size_bytes=1,
                    text="saved text",
                    metadata={},
                    updated_at=now(),
                )
            )
        c.execute(
            insert(chunks).values(
                chunk_id="0:0",
                file_id="0",
                text="saved text",
                char_start=0,
                char_end=10,
                source_origin={},
                embedding=[1.0, 0.0],
                embedding_model="test-model",
            )
        )
    store.save_configuration(
        {"embedding_model": "test-model", "chat_model": "chat-model"}
    )
    login(client)
    result = client.get("/api/workbench/home")
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["tools"]["topics"] == {
        "enabled": True,
        "reason": "1 of 3 documents ready",
    }
    assert data["tools"]["search"]["enabled"] and data["tools"]["chat"]["enabled"]
    assert (
        "saved text" not in result.text
        and "api_key" not in result.text
        and "provider.test" not in result.text
    )
    with store.transaction() as c:
        c.execute(
            insert(chunks).values(
                chunk_id="1:0",
                file_id="1",
                text="saved text",
                char_start=0,
                char_end=10,
                source_origin={},
                embedding=[1.0, 0.0, 0.0],
                embedding_model="test-model",
            )
        )
    with store.transaction() as c:
        c.execute(
            update(datasets)
            .where(datasets.c.id == "shared")
            .values(revision=datasets.c.revision + 1)
        )
    assert not client.get("/api/workbench/home").json()["tools"]["topics"]["enabled"]


def test_compatibility_check_is_cached_until_corpus_or_model_changes(client, app):
    store = app.state.store
    store.save_configuration({"embedding_model": "model-a"})
    login(client)
    checks = []

    def track(conn, cursor, statement, parameters, context, executemany):
        if "min(dimension)" in statement:
            checks.append(statement)

    event.listen(store.engine, "before_cursor_execute", track)
    try:
        assert client.get("/api/workbench/home").status_code == 200
        assert client.get("/api/workbench/home").status_code == 200
        assert len(checks) == 1
        with store.transaction() as c:
            c.execute(
                update(datasets)
                .where(datasets.c.id == "shared")
                .values(revision=datasets.c.revision + 1)
            )
        assert client.get("/api/workbench/home").status_code == 200
        assert len(checks) == 2
        store.save_configuration({"embedding_model": "model-b"})
        assert client.get("/api/workbench/home").status_code == 200
        assert len(checks) == 3
    finally:
        event.remove(store.engine, "before_cursor_execute", track)
