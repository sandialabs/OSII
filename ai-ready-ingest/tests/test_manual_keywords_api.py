def test_manual_keywords_and_reusable_sets_are_sidecar_data(client, sample_osii_object):
    file_id = sample_osii_object["file_id"]
    created = client.post(
        "/api/keyword-sets",
        json={"name": "Sensitivity", "keywords": ["Internal", "PII"]},
    )
    assert created.status_code == 200
    assert created.json()["keyword_set"]["keywords"] == ["Internal", "PII"]

    saved = client.put(
        f"/api/objects/{file_id}/keywords/manual",
        json={"keywords": ["Internal", "thermal", "internal"]},
    )
    assert saved.status_code == 200
    assert saved.json()["keywords"] == ["Internal", "thermal"]

    fetched = client.get(f"/api/objects/{file_id}/keywords/manual")
    assert fetched.json()["keywords"] == ["Internal", "thermal"]
    listed = client.get("/api/keyword-sets")
    assert listed.json()["keyword_sets"][0]["name"] == "Sensitivity"
