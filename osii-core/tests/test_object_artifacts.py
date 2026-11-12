def test_empty_tool_scope_is_rejected(client):
    response = client.post("/api/enrichment-jobs/run", json={"enricher_name": "stats_keywords", "scope": {"scope_type": "object", "file_id": "missing"}})
    assert response.status_code == 400
    assert "text" in response.json()["detail"].lower() or "documents" in response.json()["detail"].lower()
