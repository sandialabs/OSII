from pathlib import Path

import pytest

from conftest import document, login
from osii.server.auth import digest


def test_anonymous_denied_and_bootstrap_not_public(client):
    assert client.get("/health").status_code == 200
    for path in ("/api/catalog/files", "/api/admin/users", "/openapi.json", "/artifact/state/jobs.sqlite3"):
        assert client.get(path).status_code == 401


def test_reader_permissions_and_csrf(client):
    login(client, "reader")
    assert client.get("/api/catalog/files").status_code == 200
    for path in ("/api/admin/users", "/api/admin/models"):
        assert client.get(path).status_code == 403
    assert client.post("/api/admin/intake").status_code == 403
    client.headers.pop("X-CSRF-Token")
    assert client.post("/api/search", json={"query": "detector"}).status_code == 403


def test_user_lifecycle_and_last_admin(client, app):
    login(client)
    created = client.post("/api/admin/users", json={"username": "new-reader"}).json()
    password = created["temporary_password"]
    assert "password_hash" not in created["user"]
    admin = app.state.store.account(username="admin")
    assert client.patch(f'/api/admin/users/{admin["id"]}', json={"active": False}).status_code == 422
    client.post("/api/auth/logout")
    login(client, "new-reader", password)
    assert client.get("/api/catalog/files").status_code == 403
    assert client.post("/api/auth/password", json={"current_password": password, "new_password": "a-new-secure-test-password"}).status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    login(client, "new-reader", "a-new-secure-test-password")
    assert client.get("/api/catalog/files").status_code == 200


def test_disabled_account_session_revoked(client, app):
    user = login(client, "reader")
    app.state.store.change_account(user["id"], {"active": False})
    assert client.get("/api/auth/me").status_code == 401


def test_database_ingestion_search_and_citations(client, app):
    root = app.state.settings.source_root
    doc = document(app.state.store, root)
    assert not list(root.rglob(".osii"))
    login(client, "reader")
    found = client.post("/api/search", json={"query": "neutron"})
    assert found.status_code == 200, found.text
    hit = found.json()["results"][0]
    assert hit["file_id"] == doc["file_id"]
    assert doc["text"][hit["char_start"]:hit["char_end"]] == hit["text"]
    assert hit["source_origin"]["segments"][0]["source_origin"]["page"] == 1
    assert client.get(f'/api/objects/{doc["file_id"]}/source').text == doc["text"]
    assert client.post("/api/search", json={"query": "pineapple"}).json()["results"] == []


def test_paid_chat_and_fallback(client, app):
    document(app.state.store, app.state.settings.source_root)
    app.state.store.save_configuration({"chat_model": "vendor/model-id", "embedding_model": ""})
    login(client, "reader")
    result = client.post("/api/chat", json={"query": "What does the detector use?"}).json()
    assert result["provider"] == "openai" and not result["fallback_used"]
    assert result["citations"][0]["file_id"]
    result = client.post("/api/chat", json={"query": "pineapple"}).json()
    assert result["fallback_used"] and result["citations"] == []


def test_curator_ingestion_and_shared_collections(client, app):
    doc = document(app.state.store, app.state.settings.source_root)
    login(client, "curator")
    assert client.post("/api/admin/intake").status_code == 200
    created = client.post("/api/collections", json={"name": "Shared", "members": [doc["file_id"]]})
    assert created.status_code == 200
    found = client.post("/api/search", json={"query": "neutron", "scope": {"scope_type": "collection", "collection_id": created.json()["id"]}})
    assert len(found.json()["results"]) == 1
    assert client.get("/api/admin/models").status_code == 403


def test_folder_scope_is_applied_before_ranking_and_catalog_paginates(client, app):
    root = app.state.settings.source_root
    document(app.state.store, root, name="root.txt", content="Root neutron detector")
    nested = document(app.state.store, root, name="nested/report.txt", content="Nested neutron detector")
    login(client, "reader")
    all_hits = client.post("/api/search", json={"query":"neutron", "scope":{"scope_type":"folder", "folder_id":"."}}).json()["results"]
    assert len(all_hits) == 2
    scoped = client.post("/api/search", json={"query":"neutron", "scope":{"scope_type":"folder", "folder_id":"nested"}}).json()["results"]
    assert [r["file_id"] for r in scoped] == [nested["file_id"]]
    first = client.get("/api/catalog/files?limit=1").json()
    second = client.get("/api/catalog/files", params={"limit":1,"cursor":first["next_cursor"]}).json()
    assert first["items"][0]["file_id"] != second["items"][0]["file_id"]
    assert second["next_cursor"] is None


def test_model_catalog_does_not_invoke_generation(client):
    login(client)
    r = client.get("/api/admin/models/catalog")
    assert r.status_code == 200 and r.json()["models"][0]["id"] == "vendor/model-id"
    assert r.json()["generation_tested"] is False
    config = client.get("/api/admin/models").json()
    assert "secret-not-for-clients" not in str(config)
    assert config["endpoints"]["chat"]["base_url"] == "https://provider.test/v1"
    assert config["endpoints"]["embedding"]["credential_present"] is True
    assert config["endpoints"]["rerank"]["configured"] is False
    assert client.put("/api/admin/models", json={"chat_model": "vendor/model-id"}).status_code == 200
    assert client.post("/api/admin/models/test").json()["chat"]["ok"]


def test_jobs_leases_recovery_and_no_double_claim(store):
    from datetime import timedelta
    from sqlalchemy import update
    from osii.persistence.postgres import jobs, now
    jid = store.enqueue("ingest", {})
    first = store.claim("first")
    assert first["id"] == jid and store.claim("second") is None
    assert store.progress(jid, "first", "processing: report.pdf")
    assert store.job_records()[0]["logs"] == ["processing: report.pdf"]
    with store.transaction() as c:
        c.execute(update(jobs).where(jobs.c.id == jid).values(lease_until=now() - timedelta(seconds=1)))
    assert store.claim("second")["id"] == jid
    assert not store.progress(jid, "first", "stale progress")
    store.finish(jid, "first", ["stale worker"])
    assert store.job_records()[0]["status"] == "running"
    store.finish(jid, "second", ["done"])
    assert store.job_records()[0]["status"] == "done"


def test_failed_document_transaction_preserves_previous_data(store, tmp_path):
    from sqlalchemy.exc import IntegrityError
    original = document(store, tmp_path)
    replacement = {k: v for k, v in original.items() if k != "updated_at"}
    replacement["text"] = "Should roll back"
    with pytest.raises(IntegrityError):
        store.commit_document(replacement, [{"chunk_id": "bad", "file_id": "nonexistent", "text": "bad", "char_start": 0, "char_end": 3, "source_origin": {}}], {}, [])
    assert store.document(original["file_id"])["text"] == original["text"]


def test_no_source_path_escape(client, app):
    login(client)
    assert client.get("/artifact/../../etc/passwd").status_code == 404
    client.headers["Origin"] = "https://evil.test"
    assert client.post("/api/admin/intake").status_code == 403


def test_changed_original_is_not_shown_as_old_evidence(client, app):
    root = app.state.settings.source_root
    doc = document(app.state.store, root)
    (root / doc["source_relpath"]).write_text("A replacement original")
    login(client, "reader")
    assert client.get(f'/api/objects/{doc["file_id"]}/source').status_code == 409
    assert client.get(f'/api/objects/{doc["file_id"]}/texts/preferred').json()["text"] == doc["text"]


def test_restoring_previous_original_reactivates_its_identity(store, tmp_path):
    first = document(store, tmp_path, content="First neutron report")
    replacement = document(store, tmp_path, content="Replacement thermal report")
    assert first["file_id"] != replacement["file_id"]
    restored = document(store, tmp_path, content="First neutron report")
    active = store.snapshot()[1]
    assert len(active) == 1 and active[0]["file_id"] == restored["file_id"] == first["file_id"]
    assert not store.document(replacement["file_id"])["active"]


def test_empty_extraction_requires_ocr_and_can_retry(store, tmp_path):
    from osii.server.worker import IngestionError, ingest_file
    from osii.processor_sdk.models import ExtractionResponse, ProcessorDescriptor, ProcessorKind, TextSegment
    from conftest import Provider

    class Extractor:
        def __init__(self, text):
            self.text = text

        def extract(self, request):
            return ExtractionResponse(request_id=request.request_id, processor=ProcessorDescriptor(
                name="test.extractor", version="1", display_name="Test", description="Test", kind=ProcessorKind.EXTRACTOR),
                segments=[TextSegment(id="page-1", text=self.text, source_origin={"page": 1})] if self.text else [])

    path = tmp_path / "scan.txt"
    path.write_bytes(b"scan original")
    with pytest.raises(IngestionError, match="OSII_OCR_URL"):
        ingest_file(store, Provider(), Extractor(""), tmp_path, path)
    assert store.snapshot()[1] == []
    assert ingest_file(store, Provider(), Extractor(""), tmp_path, path, ocr=Extractor("OCR neutron detector")) == "processed"
    assert ingest_file(store, Provider(), Extractor(""), tmp_path, path) == "unchanged"
    assert len(store.snapshot()[1]) == 1
    assert ingest_file(store, Provider(), Extractor("Improved neutron OCR"), tmp_path, path, force=True) == "processed"
    assert store.snapshot()[1][0]["text"] == "Improved neutron OCR"


def test_paid_search_budget_keeps_lexical_search_available(client, app):
    document(app.state.store, app.state.settings.source_root)
    app.state.store.save_configuration({"chat_model": "", "embedding_model": "vendor/embedding-id"})
    user = login(client, "reader")
    for _ in range(20):
        assert app.state.store.login_allowed("search:" + user["id"], failed=True, maximum=20)
    assert client.post("/api/search", json={"query": "neutron", "mode": "hybrid"}).status_code == 429
    assert client.post("/api/search", json={"query": "neutron", "mode": "lexical"}).status_code == 200


def test_nul_extraction_is_recorded_without_shifting_citations(store, tmp_path):
    from sqlalchemy import select
    from osii.persistence.postgres import extractions
    from osii.processor_sdk.models import ExtractionResponse, ProcessorDescriptor, ProcessorKind, TextSegment
    from osii.server.worker import ingest_file
    from conftest import Provider

    class Extractor:
        def extract(self, request):
            return ExtractionResponse(request_id=request.request_id, processor=ProcessorDescriptor(
                name="test", version="1", display_name="Test", description="Test", kind=ProcessorKind.EXTRACTOR),
                segments=[TextSegment(id="p1", text="Neutron\x00detector", source_origin={"label": "page\x001"}),
                          TextSegment(id="p2", text="Second page", source_origin={"page": 2})])

    path = tmp_path / "report.pdf"
    original = b"original PDF bytes"
    path.write_bytes(original)
    store.save_configuration({"embedding_model": "test-model"})
    assert ingest_file(store, Provider(), Extractor(), tmp_path, path) == "processed"
    _, docs, rows = store.snapshot()
    doc = docs[0]
    assert doc["text"] == "Neutron\ufffddetector\nSecond page"
    assert doc["metadata"]["normalization"] == {"nul_replacements": 2, "replacement": "U+FFFD"}
    assert doc["metadata"]["segments"][1]["char_start"] == len("Neutron\x00detector\n")
    assert all(doc["text"][row["char_start"]:row["char_end"]] == row["text"] for row in rows)
    assert all(row["embedding"] for row in rows)
    with store.engine.connect() as c:
        response = c.execute(select(extractions.c.response)).scalar_one()
    assert response["segments"][0]["source_origin"]["label"] == "page\ufffd1"
    assert path.read_bytes() == original


@pytest.mark.parametrize("failure", ["extractor", "embedding"])
def test_batch_continues_after_failed_pdf_and_resume_skips_successes(store, tmp_path, failure):
    import threading
    from conftest import Provider
    from osii.model_provider import ProviderError
    from osii.processor_sdk.client import ProcessorClientError
    from osii.processor_sdk.models import ExtractionResponse, ProcessorDescriptor, ProcessorKind, TextSegment
    from osii.server.worker import ingest_batch

    class Extractor:
        def extract(self, request):
            if request.document.filename == "a-bad.pdf" and failure == "extractor":
                raise ProcessorClientError("sensitive processor response must not be logged")
            return ExtractionResponse(request_id=request.request_id, processor=ProcessorDescriptor(
                name="test", version="1", display_name="Test", description="Test", kind=ProcessorKind.EXTRACTOR),
                segments=[TextSegment(id="p1", text=request.document.filename, source_origin={"page": 1})])

    class Embeddings(Provider):
        def embed(self, model, texts):
            if texts[0] == "a-bad.pdf":
                raise ProviderError("The provider rate limit was reached")
            return super().embed(model, texts)

    for name in ("a-bad.pdf", "b-good.pdf", "c-good.pdf"):
        (tmp_path / name).write_text(name)
    store.save_configuration({"embedding_model": "test-model"})
    jid = store.enqueue("ingest", {})
    store.claim("test-worker")
    logs = []
    def report(entry):
        logs.append(entry)
        assert store.progress(jid, "test-worker", entry)
    kwargs = dict(report=report, stopping=threading.Event())
    assert ingest_batch(store, Embeddings(), Extractor(), tmp_path, **kwargs)
    assert ("failed: a-bad.pdf:" if failure == "extractor" else "text_only: a-bad.pdf") in logs[1]
    assert "sensitive processor response" not in str(logs)
    assert logs[-1] == ("Batch completed: processed=2, unchanged=0, failed=1" if failure == "extractor"
                        else "Batch completed: processed=2, unchanged=0, failed=0, text_only=1")
    assert store.job_records()[0]["logs"] == logs
    _, docs, rows = store.snapshot()
    assert {d["filename"] for d in docs} == ({"b-good.pdf", "c-good.pdf"} if failure == "extractor" else {"a-bad.pdf", "b-good.pdf", "c-good.pdf"})
    assert len([row for row in rows if row["embedding"]]) == 2
    assert ingest_batch(store, Embeddings(), Extractor(), tmp_path, **kwargs)
    assert logs[-1] == ("Batch completed: processed=0, unchanged=2, failed=1" if failure == "extractor"
                        else "Batch completed: processed=0, unchanged=2, failed=0, text_only=1")


def test_missing_shared_source_is_not_reported_as_success(store, tmp_path):
    import threading
    from osii.server.worker import IngestionError, ingest_batch
    with pytest.raises(IngestionError, match="source directory is unavailable"):
        ingest_batch(store, None, None, tmp_path / "disconnected", report=lambda entry: None,
                     stopping=threading.Event())
