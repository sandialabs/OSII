"""Shared reader integration against the actual migrated hosted schema."""
import json

from conftest import document, login
from sqlalchemy import insert

from osii.domain.read.contracts import ReadScope
from osii.domain.read.postgres import PostgresLibraryReader
from osii.persistence.postgres import artifacts


def test_migrated_document_reads_keep_identity_text_spans_and_records(app):
    store = app.state.store
    doc = document(store, app.state.settings.source_root)
    before = store.snapshot()
    reader = PostgresLibraryReader(store.engine)
    result = reader.get_document(doc["file_id"])
    representation = reader.get_representation(doc["file_id"])
    assert result.source_relpath == doc["source_relpath"]
    assert representation.representation_id == doc["metadata"]["primary_extraction_id"]
    assert representation.text == doc["text"]
    assert representation.segments[0].text == doc["text"]
    assert representation.segments[0].source_origin["page"] == 1
    assert reader.list_documents(ReadScope("object", doc["file_id"])).total == 1
    assert store.snapshot() == before


def test_hosted_preferred_and_artifact_reads_preserve_auth_and_response_shapes(client, app):
    store = app.state.store
    doc = document(store, app.state.settings.source_root)
    file_id = doc["file_id"]
    payload = {"artifact_type": "table", "title": "Measurements", "columns": [], "rows": []}
    with store.transaction() as conn:
        conn.execute(insert(artifacts).values(id="table-output", file_id=file_id, kind="table", payload=payload))
    for suffix in ("texts/preferred", "artifacts"):
        assert client.get(f"/api/objects/{file_id}/{suffix}").status_code == 401
    login(client, "reader")
    preferred = client.get(f"/api/objects/{file_id}/texts/preferred")
    assert preferred.json() == {"file_id": file_id, "representation": "primary extraction",
        "kind": "canonical_extracted_text", "text": doc["text"]}
    returned = client.get(f"/api/objects/{file_id}/artifacts").json()["items"]
    assert returned == [{"id": "table-output", "file_id": file_id, "kind": "table", "payload": payload}]
    reader = PostgresLibraryReader(store.engine)
    assert json.loads(reader.get_artifact(file_id, "table-output").data) == payload
    assert reader.list_artifacts(file_id).items[0].kind == "table"
    assert client.get("/api/objects/missing/texts/preferred").status_code == 404
