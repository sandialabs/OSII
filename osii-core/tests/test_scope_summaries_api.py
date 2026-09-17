def test_scope_summaries_root(client, sample_osii_object):
    response = client.post(
        "/api/scopes/summaries",
        json={
            "scope": {
                "scope_type": "root",
            }
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "summaries" in data
    assert len(data["summaries"]) >= 1
    assert data["summaries"][0]["file_id"] == sample_osii_object["file_id"]


def test_scope_summaries_collection(client, temp_osii_root, sample_osii_object):
    from osii.domain.scopes.collections import create_collection, add_documents_to_collection

    file_id = sample_osii_object["file_id"]
    collection = create_collection(
        temp_osii_root,
        name="scope-summary-test",
        description="test",
        kind="manual",
        color=None,
    )
    add_documents_to_collection(temp_osii_root, collection["id"], [file_id])

    response = client.post(
        "/api/scopes/summaries",
        json={
            "scope": {
                "scope_type": "collection",
                "collection_id": collection["id"],
            }
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "summaries" in data
    assert len(data["summaries"]) == 1
    assert data["summaries"][0]["file_id"] == file_id