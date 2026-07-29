from osii.enrichment.stats_keywords import StatsKeywordsEnricher


def test_list_object_enrichments_api(client, temp_osii_root, sample_osii_object):
    file_id = sample_osii_object["file_id"]

    enricher = StatsKeywordsEnricher()
    enricher.enrich(
        osii_store=temp_osii_root,
        scope={"scope_type": "object", "file_id": file_id},
        enricher_config={"top_k": 10},
    )

    response = client.post(
        "/api/enrichments/list",
        json={"scope_type": "object", "file_id": file_id},
    )
    assert response.status_code == 200
    data = response.json()
    assert "enrichments" in data
    assert len(data["enrichments"]) >= 1


def test_get_object_enrichment_payload_api(client, temp_osii_root, sample_osii_object):
    file_id = sample_osii_object["file_id"]

    enricher = StatsKeywordsEnricher()
    enricher.enrich(
        osii_store=temp_osii_root,
        scope={"scope_type": "object", "file_id": file_id},
        enricher_config={"top_k": 10},
    )

    response = client.get(f"/api/enrichments/objects/{file_id}/keywords--stats_keywords.json")
    assert response.status_code == 200
    data = response.json()
    assert data["file_id"] == file_id
    assert data["filename"] == "keywords--stats_keywords.json"
    assert "keywords" in data["data"]
    assert data["data"]["artifact_type"] == "table"


def test_scope_enrichment_payload_endpoint(client, temp_osii_root, sample_osii_object):
    file_id = sample_osii_object["file_id"]
    StatsKeywordsEnricher().enrich(
        osii_store=temp_osii_root,
        scope={"scope_type": "object", "file_id": file_id},
        enricher_config={"top_k": 10},
    )

    response = client.post(
        "/api/enrichments/payload",
        json={
            "scope": {"scope_type": "object", "file_id": file_id},
            "filename": "keywords--stats_keywords.json",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["scope_type"] == "object"
    assert data["data"]["artifact_type"] == "table"
