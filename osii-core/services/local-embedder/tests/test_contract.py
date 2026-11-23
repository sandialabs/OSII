import math
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_hashing_contract_determinism_order_and_norm():
    assert client.get("/v1/descriptor").json()["name"] == "local.hashing"
    assert "/v1/embed" in client.get("/openapi.json").json()["paths"]
    payload = {"request_id": "r1", "inputs": [{"id": "b", "text": "alpha beta"}, {"id": "a", "text": "alpha beta"}]}
    first = client.post("/v1/embed", json=payload).json()
    second = client.post("/v1/embed", json=payload).json()
    assert first == second
    assert [row["id"] for row in first["vectors"]] == ["b", "a"]
    assert all(row["dimensions"] == 384 for row in first["vectors"])
    assert math.isclose(sum(x*x for x in first["vectors"][0]["vector"]), 1.0)

def test_invalid_payload_is_422():
    assert client.post("/v1/embed", json={}).status_code == 422
