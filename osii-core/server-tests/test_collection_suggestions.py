import json
from fastapi.testclient import TestClient
from sqlalchemy import insert, update
from conftest import login
from osii.persistence.postgres import documents, now
from osii.server.api import create_app


def seed(store):
    topics = [
        "garden soil vegetable compost seed",
        "forest timber tree conservation woodland",
        "music piano orchestra symphony composer",
    ]
    with store.transaction() as connection:
        for group, words in enumerate(topics):
            for i in range(5):
                identity = f"{group}-{i}"
                connection.execute(
                    insert(documents).values(
                        file_id=identity,
                        source_relpath=identity + ".txt",
                        filename=identity + ".txt",
                        media_type="text/plain",
                        active=True,
                        sha256=identity,
                        size_bytes=1,
                        text=words * 20,
                        metadata={},
                        updated_at=now(),
                    )
                )


def test_automatic_suggestions_are_authenticated_cached_and_do_not_generate_or_write_collections(
    client, app, monkeypatch
):
    seed(app.state.store)
    assert client.get("/api/collection-suggestions").status_code == 401
    login(client, "reader")
    first = client.get("/api/collection-suggestions")
    assert first.status_code == 200, first.text
    result = first.json()
    assert result["considered_documents"] == 15 and len(result["suggestions"]) >= 3
    assert not result["can_prompt"]
    assert client.get("/api/collections").json()["items"] == []
    import osii.api.collection_suggestion_routes as routes

    def forbidden(*args, **kwargs):
        raise AssertionError("Repeated GET recomputed clustering or called a model")

    monkeypatch.setattr(routes, "topic_proposals", forbidden)
    assert client.get("/api/collection-suggestions").json() == result
    item = result["suggestions"][0]
    saved = client.post(
        "/api/collections",
        json={
            "name": item["name"],
            "description": item["description"],
            "members": item["file_ids"],
        },
    )
    assert saved.status_code == 200 and saved.json()["visibility"] == "private"


def test_cache_invalidates_when_saved_descriptions_change(client, app):
    seed(app.state.store)
    login(client)
    client.get("/api/collection-suggestions")
    before = app.state.store.setting("collection_suggestions", {})["identity"]
    with app.state.store.transaction() as connection:
        connection.execute(
            update(documents)
            .where(documents.c.file_id == "0-0")
            .values(text="changed saved description")
        )
    assert client.get("/api/collection-suggestions").status_code == 200
    assert app.state.store.setting("collection_suggestions", {})["identity"] != before


def test_prompt_requires_csrf_and_configuration_and_returns_selection_only(app):
    store = app.state.store
    seed(store)

    class Model:
        calls = 0

        def chat(self, model, messages, **kwargs):
            self.calls += 1
            assert model == "chat-test"
            manifest = json.loads(messages[1]["content"])
            assert manifest["goal"] == "Focus on forest conservation"
            return json.dumps(
                {
                    "collections": [
                        {
                            "name": "Forest reading",
                            "description": "Related forestry documents",
                            "document_ids": [0, 1],
                        }
                    ]
                }
            ), {}

    model = Model()
    custom = create_app(app.state.settings, store, model)
    with TestClient(custom) as client:
        login(client, "reader")
        assert (
            client.post(
                "/api/collection-suggestions", json={"prompt": "forests"}
            ).status_code
            == 409
        )
        store.save_configuration({"chat_model": "chat-test"})
        csrf = client.headers.pop("X-CSRF-Token")
        assert (
            client.post(
                "/api/collection-suggestions", json={"prompt": "forests"}
            ).status_code
            == 403
        )
        client.headers["X-CSRF-Token"] = csrf
        result = client.post(
            "/api/collection-suggestions",
            json={"prompt": "Focus on forest conservation"},
        )
        assert result.status_code == 200, result.text
        assert result.json()["guided"] and model.calls == 1
        assert all(
            fid.startswith("1-") for fid in result.json()["suggestions"][0]["file_ids"]
        )
        assert client.get("/api/collections").json()["items"] == []
        assert (
            client.post(
                "/api/collection-suggestions", json={"prompt": "x" * 2001}
            ).status_code
            == 422
        )
        assert model.calls == 1
