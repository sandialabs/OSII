def test_search_post_scope_aware(client, monkeypatch):
    def fake_dashboard_search(osii_root, *, query, mode, top_k=10, scope=None, group_by=None):
        assert query == "thermal calibration drift"
        assert mode == "hybrid"
        assert scope["scope_type"] == "collection"
        assert group_by == "file"
        return (
            "lexical",
            [
                {
                    "file_id": "sha256-test123",
                    "filename": "example.pdf",
                    "source_relpath": "reports/example.pdf",
                    "snippet": "Thermal calibration drift was reduced.",
                    "score": 0.9,
                    "match_type": "hybrid",
                    "chunk_id": "chunk-sha256-test123-000001",
                    "chunk_method": "paragraph",
                    "chunk_index": 1,
                    "char_start": 0,
                    "char_end": 38,
                    "source_text_representation": "canonical",
                    "source_text_kind": "canonical_extracted_text",
                    "source_origin": {
                        "grounding_type": "text_span",
                        "char_start": 0,
                        "char_end": 38,
                    },
                    "collections": [],
                }
            ],
        )

    monkeypatch.setattr("osii.api.search_routes.dashboard_search", fake_dashboard_search)

    response = client.post(
        "/api/search",
        json={
            "query": "thermal calibration drift",
            "mode": "hybrid",
            "top_k": 5,
            "scope": {
                "scope_type": "collection",
                "collection_id": "col-abc123def456",
            },
            "group_by": "file",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "thermal calibration drift"
    assert data["mode"] == "hybrid"
    assert data["retrieval_mode_used"] == "lexical"
    assert data["group_by"] == "file"
    assert data["scope"]["scope_type"] == "collection"
    assert len(data["results"]) == 1