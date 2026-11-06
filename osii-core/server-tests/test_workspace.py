"""Hosted workspace permissions, source boundaries, and database-vector exploration."""
import threading
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import text, update

from conftest import document, login
from osii.domain.topics import TopicIndexUnavailable, project_documents, topic_map
from osii.persistence.postgres import chunks
from osii.server.sources import browse, resolve_directory


def test_reader_collections_are_private_across_all_scoped_apis(client, app):
    doc = document(app.state.store, app.state.settings.source_root)
    owner = login(client, "reader")
    collection = client.post("/api/collections", json={"name": "My evidence", "members": [doc["file_id"]]}).json()
    assert collection["owner_id"] == owner["id"] and collection["visibility"] == "private"
    scope = {"scope_type": "collection", "collection_id": collection["id"]}
    assert client.post("/api/search", json={"query": "neutron", "scope": scope}).json()["results"]
    assert client.get("/api/catalog/files", params={"collection_id": collection["id"]}).json()["total"] == 1
    for other in ("curator", "admin"):
        login(client, other)
        assert client.get("/api/collections").json()["items"] == []
        for path in ("/api/search", "/api/chat", "/api/topics/map", "/api/topics/related"):
            r = client.post(path, json={"query": "neutron", "scope": scope, "file_id": doc["file_id"]})
            assert r.status_code == 422 and r.json()["detail"] == "Collection not found", r.text
        assert client.get("/api/catalog/files", params={"collection_id": collection["id"]}).status_code == 422
        assert client.put(f'/api/collections/{collection["id"]}', json={"name": "stolen"}).status_code == 404
        assert client.delete(f'/api/collections/{collection["id"]}').status_code == 404
    login(client, "reader")
    assert client.delete(f'/api/collections/{collection["id"]}').status_code == 200
    assert app.state.store.document(doc["file_id"])


def test_publication_and_membership_permissions(client, app):
    store = app.state.store
    doc = document(store, app.state.settings.source_root)
    login(client, "reader")
    assert client.post("/api/collections", json={"name": "Published", "visibility": "shared"}).status_code == 403
    assert client.post("/api/collections", json={"name": "Unknown", "members": ["missing"]}).status_code == 422
    private = client.post("/api/collections", json={"name": "Same name"}).json()
    assert client.put(f'/api/collections/{private["id"]}', json={"name": "x", "visibility": "shared"}).status_code == 403
    login(client, "curator")
    personal = client.post("/api/collections", json={"name": "Same name"}).json()
    assert personal["visibility"] == "private"
    payload = {"name": "Same name", "members": [doc["file_id"], doc["file_id"]], "visibility": "shared"}
    published = client.put(f'/api/collections/{personal["id"]}', json=payload).json()
    assert published["members"] == [doc["file_id"]]
    login(client, "reader")
    items = client.get("/api/collections").json()["items"]
    assert len(items) == 2
    assert not next(c for c in items if c["id"] == published["id"])["can_manage"]
    assert client.put(f'/api/collections/{published["id"]}', json=payload).status_code == 403
    assert client.delete(f'/api/collections/{published["id"]}').status_code == 403
    login(client, "admin")
    assert client.put(f'/api/collections/{published["id"]}', json={**payload, "visibility": "private"}).status_code == 403
    assert client.put(f'/api/collections/{published["id"]}', json={**payload, "members": []}).status_code == 200
    assert client.get("/api/catalog/files", params={"collection_id": published["id"]}).json()["total"] == 0


def test_source_browsing_selection_and_job_capture(client, app):
    root = app.state.settings.source_root
    (root / "first").mkdir()
    (root / "second").mkdir()
    (root / "first" / "report.txt").write_text("source text")
    (root / ".private").mkdir()
    (root / "escape").symlink_to(root.parent, target_is_directory=True)
    login(client, "reader")
    assert client.get("/api/admin/source").status_code == 403
    assert client.get("/api/admin/source/browse").status_code == 403
    assert client.put("/api/admin/source", json={"directory": "first"}).status_code == 403
    login(client)
    listing = client.get("/api/admin/source/browse").json()
    assert {item["name"] for item in listing["items"]} == {"first", "second"}
    assert client.put("/api/admin/source", json={"directory": "../outside"}).status_code == 422
    assert client.put("/api/admin/source", json={"directory": "/etc"}).status_code == 422
    assert client.put("/api/admin/source", json={"directory": "escape"}).status_code == 422
    assert client.put("/api/admin/source", json={"directory": "first"}).status_code == 200
    r = client.get("/api/admin/source").json()
    assert r["directory"] == "first" and r["available"] and r["readable"]
    assert r["statistics"]["documents"] == 0
    assert "secret-not-for-clients" not in str(r)
    login(client, "curator")
    assert client.put("/api/admin/source", json={"directory": "second"}).status_code == 403
    jid = client.post("/api/admin/intake", json={"force": False}).json()["id"]
    login(client)
    assert client.put("/api/admin/source", json={"directory": "second"}).status_code == 200
    job = next(j for j in app.state.store.job_records() if j["id"] == jid)
    assert job["payload"] == {"source_directory": "first", "force": False}
    (root / "second").rmdir()
    assert not client.get("/api/admin/source").json()["available"]
    assert client.post("/api/admin/intake").status_code == 422


def test_bounded_source_pages(tmp_path):
    for name in ("a.txt", "b.txt", "c.txt"):
        (tmp_path / name).write_text(name)
    first = browse(tmp_path, ".", limit=2)
    second = browse(tmp_path, ".", first["next_cursor"], limit=2)
    assert [i["name"] for i in first["items"]+second["items"]] == ["a.txt", "b.txt", "c.txt"]
    assert second["next_cursor"] is None
    for value in ("../escape", "/tmp", ".hidden", "nested/../../escape"):
        with pytest.raises(ValueError):
            resolve_directory(tmp_path, value)


def test_selected_processing_folder_preserves_mounted_root_identity(store, tmp_path):
    from conftest import Provider
    from osii.server.worker import ingest_batch
    from osii.processor_sdk.models import ExtractionResponse, ProcessorDescriptor, ProcessorKind, TextSegment
    class Extractor:
        def extract(self, request):
            return ExtractionResponse(request_id=request.request_id, processor=ProcessorDescriptor(
                name="test", version="1", display_name="Test", description="Test", kind=ProcessorKind.EXTRACTOR),
                segments=[TextSegment(id="p1", text=request.document.filename)])
    (tmp_path / "chosen").mkdir()
    (tmp_path / "chosen/report.txt").write_text("chosen report")
    (tmp_path / "outside.txt").write_text("other report")
    assert not ingest_batch(store, Provider(), Extractor(), tmp_path, source_directory="chosen", report=lambda _: None, stopping=threading.Event())
    docs = store.snapshot()[1]
    assert [d["source_relpath"] for d in docs] == ["chosen/report.txt"]


def test_topics_use_only_current_database_vectors_and_never_call_provider(client, app, monkeypatch):
    store, root = app.state.store, app.state.settings.source_root
    store.save_configuration({"embedding_model": "test-embeddings"})
    docs = [document(store, root, name=f"folder/{i}.txt", content=f"neutron document {i}") for i in range(3)]
    vectors = ([1, 0], [0.8, 0.6], [-1, 0])
    with store.transaction() as c:
        for doc, vector in zip(docs, vectors):
            c.execute(update(chunks).where(chunks.c.file_id == doc["file_id"]).values(embedding=vector))
    def forbidden(*args, **kwargs):
        pytest.fail("Topic exploration must not call the provider")
    from conftest import Provider
    monkeypatch.setattr(Provider, "embed", forbidden)
    monkeypatch.setattr(Provider, "chat", forbidden)
    login(client, "reader")
    mapped = client.post("/api/topics/map", json={}).json()
    assert mapped["indexed_count"] == mapped["shown_count"] == 3
    assert all(np.isfinite([point["x"], point["y"]]).all() for point in mapped["points"])
    related = client.post("/api/topics/related", json={"file_id": docs[0]["file_id"]}).json()
    assert [d["file_id"] for d in related["results"]] == [docs[1]["file_id"], docs[2]["file_id"]]
    assert related["results"][0]["similarity"] == pytest.approx(0.8)
    collection = client.post("/api/collections", json={"name": "Scoped", "members": [docs[0]["file_id"]]}).json()
    scope = {"scope_type": "collection", "collection_id": collection["id"]}
    assert client.post("/api/topics/map", json={"scope": scope}).json()["scope_count"] == 1
    assert client.post("/api/topics/related", json={"scope": scope, "file_id": docs[2]["file_id"]}).status_code == 409
    store.save_configuration({"embedding_model": "changed-model"})
    changed = client.post("/api/topics/map", json={}).json()
    assert changed["indexed_count"] == 0 and changed["stale_count"] == 3
    store.save_configuration({"embedding_model": ""})
    assert client.post("/api/topics/map", json={}).status_code == 409


def test_topic_projection_degenerate_and_invalid_vectors():
    coordinates, variance = project_documents(np.array([[1, 0], [1, 0]]))
    assert not coordinates.any() and variance == 0
    docs = [{"file_id": str(i), "filename": str(i), "source_relpath": str(i)} for i in range(2)]
    rows = [{"file_id": str(i), "embedding_model": "m", "embedding": [1, 0]} for i in range(2)]
    assert topic_map(docs, rows, "m", 1) == topic_map(docs, rows, "m", 1)
    rows[1]["embedding"] = [1, 0, 0]
    with pytest.raises(TopicIndexUnavailable, match="dimensions disagree"):
        topic_map(docs, rows, "m", 1)
    rows[1]["embedding"] = [float("nan"), 0]
    with pytest.raises(TopicIndexUnavailable, match="Invalid indexed vectors"):
        topic_map(docs, rows, "m", 1)
    assert topic_map([], [], "m", 0)["points"] == []


def test_existing_collections_survive_upgrade_as_shared(store):
    from alembic import command
    from alembic.config import Config
    with store.transaction() as c:
        c.execute(text("DROP SCHEMA public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "osii/persistence/migrations"))
    config.attributes["database_url"] = store.engine.url.render_as_string(hide_password=False)
    command.upgrade(config, "0001_server")
    with store.transaction() as c:
        c.execute(text("INSERT INTO collections(id,name,description,members) VALUES ('legacy','Legacy','Existing shared work','[]')"))
    command.upgrade(config, "head")
    store.ready()
    collection = store.collection_records()[0]
    assert collection["id"] == "legacy" and collection["visibility"] == "shared" and collection["owner_id"] is None


def test_stale_shared_edit_cannot_republish_private_collection(client, app):
    login(client, "curator")
    shared = client.post("/api/collections", json={"name": "Shared", "visibility": "shared"}).json()
    previous = {k: v for k, v in shared.items() if k != "can_manage"}
    assert client.put(f'/api/collections/{shared["id"]}', json={"name": "Now private"}).status_code == 200
    assert not app.state.store.save_collection(previous, previous)
    assert not app.state.store.delete_collection(previous)
    assert app.state.store.collection_records() == []


def test_collection_remains_editable_after_original_is_replaced(client, app):
    store, root = app.state.store, app.state.settings.source_root
    old = document(store, root)
    login(client, "reader")
    collection = client.post("/api/collections", json={"name": "Evidence", "members": [old["file_id"]]}).json()
    document(store, root, content="Replacement neutron report")
    r = client.put(f'/api/collections/{collection["id"]}', json={"name": "Renamed evidence", "members": collection["members"]})
    assert r.status_code == 200 and r.json()["members"] == [old["file_id"]]
    assert client.get("/api/catalog/files", params={"collection_id": collection["id"]}).json()["total"] == 0
    assert client.put(f'/api/collections/{collection["id"]}', json={"name": "Renamed evidence", "members": []}).status_code == 200
