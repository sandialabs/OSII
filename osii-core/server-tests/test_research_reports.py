import json

from conftest import Provider, document, login


def test_report_requires_authentication(client):
    result = client.post("/api/research/report", json={"scope": {"scope_type": "object", "file_id": "x"}, "prompt": "Explain"})
    assert result.status_code == 401


def test_reader_report_uses_postgres_evidence_and_configured_model(client, app, monkeypatch):
    doc = document(app.state.store, app.state.settings.source_root)
    app.state.store.save_configuration({"chat_model": "writer"})
    def complete(self, model, messages, max_tokens=900):
        assert model == "writer"
        assert max_tokens == 6000
        evidence = json.loads(messages[1]["content"])["evidence"]
        assert evidence[0]["excerpt"] == doc["text"]
        return "# Detector report\n\nThe detector uses thermal neutrons. [[S1]]", {}
    monkeypatch.setattr(Provider, "chat", complete)
    login(client, "reader")
    result = client.post("/api/research/report", json={"scope": {"scope_type": "object", "file_id": doc["file_id"]}, "prompt": "Explain the detector"})
    assert result.status_code == 200, result.text
    source = result.json()["sources"][0]
    assert source["excerpt"] == doc["text"]
    assert source["page"] == 1
    assert source["representation_id"] == doc["metadata"]["primary_extraction_id"]
    assert "## Bibliography" in result.json()["markdown"]


def test_report_cannot_read_someone_elses_private_collection(client, app):
    login(client, "curator")
    response = client.post("/api/collections", json={"name": "Private", "members": [], "visibility": "private"})
    assert response.status_code == 200, response.text
    collection = response.json()
    login(client, "reader")
    result = client.post("/api/research/report", json={"scope": {"scope_type": "collection", "collection_id": collection["id"]}, "prompt": "Explain"})
    assert result.status_code == 404
