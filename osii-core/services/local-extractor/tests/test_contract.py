import base64
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_contract_and_text_extraction():
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/v1/descriptor").json()["name"] == "local.native-text"
    assert "/v1/extract" in client.get("/openapi.json").json()["paths"]
    response = client.post("/v1/extract", json={"request_id": "r1", "document": {"file_id": "f1", "filename": "notes.txt", "media_type": "text/plain", "content_base64": base64.b64encode(b"grounded text").decode()}})
    assert response.status_code == 200
    assert response.json()["segments"][0]["source_origin"]["unit_type"] == "chunk"

def test_invalid_payload_is_422():
    assert client.post("/v1/extract", json={}).status_code == 422
