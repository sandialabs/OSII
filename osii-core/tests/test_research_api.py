def test_report_endpoint_reads_sidecars_and_round_trips_canonical_links(client, sample_osii_object, temp_osii_root, monkeypatch):
    from osii.domain.catalog_db import upsert_document
    file_id = sample_osii_object["file_id"]
    # The report reader lists only completed/partial processing records.
    (temp_osii_root / "objects" / file_id / "provenance.toml").write_text('[provenance]\nstatus = "done"\n')
    upsert_document(temp_osii_root, file_id)
    monkeypatch.setenv("CHAT_PROVIDER", "extractive")
    response = client.post("/api/research/report", json={
        "scope": {"scope_type": "object", "file_id": file_id}, "prompt": "Explain calibration drift"})
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["provider"] == "extractive"
    assert report["sources"][0]["excerpt"] == "Thermal calibration drift was reduced."
    source = report["sources"][0]
    assert source["page"] == 1
    text = client.get(f"/api/objects/{file_id}/extractions/canonical/texts")
    assert text.status_code == 200
    assert text.json()["text"][source["char_start"]:source["char_end"]] == source["excerpt"]


def test_report_endpoint_rejects_invalid_scope_and_empty_text(client):
    assert client.post("/api/research/report", json={"scope": {"scope_type": "root"}, "prompt": "Report"}).status_code == 422
    response = client.post("/api/research/report", json={"scope": {"scope_type": "collection", "collection_id": "empty"}, "prompt": "Report"})
    assert response.status_code == 422
    assert "No extracted text" in response.json()["detail"]
