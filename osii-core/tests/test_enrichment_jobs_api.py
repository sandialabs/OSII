def test_invalid_scope_is_rejected_before_queueing(client):
    response = client.post("/api/enrichment-jobs/run", json={"enricher_name": "stats_keywords", "scope": {"scope_type": "object", "file_id": "../escape"}})
    assert response.status_code == 400
    assert "Invalid file_id" in response.json()["detail"]
