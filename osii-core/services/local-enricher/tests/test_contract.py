from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_standard_table_contract():
    assert client.get("/v1/descriptor").json()["name"] == "local.stats-keywords"
    assert "/v1/enrich" in client.get("/openapi.json").json()["paths"]
    response = client.post("/v1/enrich", json={"request_id": "r1", "scope": {"scope_type": "object", "scope_id": "f1", "documents": [{"file_id": "f1", "filename": "a.txt", "text": "alpha alpha beta"}]}})
    assert response.status_code == 200
    table = response.json()["artifacts"][0]["standard_data"]
    assert table["artifact_type"] == "table"
    assert table["rows"][0]["keywords"][0] == "alpha"

def test_invalid_payload_is_422():
    assert client.post("/v1/enrich", json={}).status_code == 422
