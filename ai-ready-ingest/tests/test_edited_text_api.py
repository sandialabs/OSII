def test_get_edited_text_default(client, sample_osii_object):
    file_id = sample_osii_object["file_id"]

    response = client.get(f"/api/objects/{file_id}/texts/edited")
    assert response.status_code == 200
    data = response.json()
    assert data["file_id"] == file_id
    assert data["exists"] is False
    assert data["representation"] == "edited"
    assert data["segments"] == []


def test_put_edited_text_segments(client, sample_osii_object):
    file_id = sample_osii_object["file_id"]

    response = client.put(
        f"/api/objects/{file_id}/texts/edited",
        json={
            "segments": [
                {
                    "id": "seg-000001",
                    "text": "Corrected text for this segment."
                }
            ]
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["file_id"] == file_id
    assert data["updated"] is True
    assert data["segments"][0]["id"] == "seg-000001"
    assert data["stale"]["embeddings"] is True
    assert data["stale"]["search_chunks"] is True


def test_get_preferred_text_uses_edited(client, sample_osii_object):
    file_id = sample_osii_object["file_id"]

    put_response = client.put(
        f"/api/objects/{file_id}/texts/edited",
        json={
            "segments": [
                {
                    "id": "seg-000001",
                    "text": "Corrected text for this segment."
                }
            ]
        },
    )
    assert put_response.status_code == 200

    response = client.get(f"/api/objects/{file_id}/texts/preferred")
    assert response.status_code == 200
    data = response.json()
    assert data["representation"] == "edited"
    assert data["kind"] == "edited_text"
    assert "Corrected text for this segment." in data["text"]


def test_delete_edited_text(client, sample_osii_object):
    file_id = sample_osii_object["file_id"]

    client.put(
        f"/api/objects/{file_id}/texts/edited",
        json={
            "segments": [
                {
                    "id": "seg-000001",
                    "text": "Corrected text for this segment."
                }
            ]
        },
    )

    response = client.delete(f"/api/objects/{file_id}/texts/edited")
    assert response.status_code == 200
    data = response.json()
    assert data["file_id"] == file_id
    assert data["removed"] is True
    assert data["stale"]["embeddings"] is True
    assert data["stale"]["search_chunks"] is True