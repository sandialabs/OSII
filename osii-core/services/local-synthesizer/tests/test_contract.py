from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_contract_and_cited_preview():
    assert client.get("/health").status_code == 200
    assert client.get("/v1/descriptor").json()["name"] == "local.extractive-preview"
    assert "/v1/synthesize" in client.get("/openapi.json").json()["paths"]
    response = client.post("/v1/synthesize", json={"request_id": "r1", "scope": {"scope_type": "object", "scope_id": "f1", "documents": [{"file_id": "f1", "filename": "a.txt", "text": "Grounded source sentence."}]}})
    assert response.status_code == 200
    assert response.json()["citations"][0]["file_id"] == "f1"

def test_invalid_payload_is_422():
    assert client.post("/v1/synthesize", json={}).status_code == 422


def test_preview_citation_uses_original_offsets_after_whitespace_cleanup():
    source = "   alpha\n\n beta    gamma delta"
    response = client.post("/v1/synthesize", json={"request_id": "grounded", "scope": {
        "scope_type": "object", "scope_id": "f1", "documents": [{"file_id": "f1", "filename": "a", "text": source}]},
        "config": {"max_chars_per_document": 13}})
    assert response.status_code == 200
    data = response.json()
    citation = data["citations"][0]
    excerpt = data["markdown"].split("\n\n", 1)[1]
    assert " ".join(source[citation["char_start"]:citation["char_end"]].split()) == excerpt
