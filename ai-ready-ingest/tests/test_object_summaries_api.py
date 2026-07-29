def test_object_summaries_route(client, sample_osii_object):
    file_id = sample_osii_object["file_id"]

    response = client.post(
        "/api/objects/summaries",
        json={
            "file_ids": [file_id],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "summaries" in data
    assert len(data["summaries"]) == 1

    summary = data["summaries"][0]
    assert summary["file_id"] == file_id
    assert "filename" in summary
    assert "source_relpath" in summary
    assert "source_file_relpath" in summary
    assert "processing" in summary
    assert "source_state" in summary
    assert "has_preferred_text" in summary
    assert "preferred_text_kind" in summary
    assert "has_synthesis" in summary
    assert "has_enrichments" in summary
    assert "preview_available" in summary
    assert "synthesis_preview" in summary