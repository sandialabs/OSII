def test_enrichment_job_api_starts_job(client, monkeypatch, sample_osii_object):
    class FakeEnricher:
        def enrich(self, *, osii_store, scope, enricher_config=None):
            return {
                "result": {
                    "scope_type": scope["scope_type"],
                    "kind": "keywords",
                    "method": "stats_keywords",
                }
            }

    monkeypatch.setattr("osii.api.enrichment_jobs_routes.resolve_enricher", lambda name: FakeEnricher())

    response = client.post(
        "/api/enrichment-jobs/run",
        json={
            "enricher_name": "stats_keywords",
            "scope": {
                "scope_type": "object",
                "file_id": sample_osii_object["file_id"],
            },
            "enricher_config": {"top_k": 10},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["enricher_name"] == "stats_keywords"
    assert "run_id" in data