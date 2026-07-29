def test_scope_artifacts_root(client, sample_osii_object):
    response = client.post(
        "/api/scopes/artifacts",
        json={
            "scope": {
                "scope_type": "root",
            }
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "scope" in data
    assert "artifact_summary" in data
    assert "actions" in data
    assert data["scope"]["scope_type"] == "root"


def test_scope_artifacts_collection(client, temp_osii_root, sample_osii_object):
    from osii.domain.scopes.collections import create_collection, add_documents_to_collection

    file_id = sample_osii_object["file_id"]
    collection = create_collection(
        temp_osii_root,
        name="scope-artifacts-collection",
        description="test",
        kind="manual",
        color=None,
    )
    add_documents_to_collection(temp_osii_root, collection["id"], [file_id])

    response = client.post(
        "/api/scopes/artifacts",
        json={
            "scope": {
                "scope_type": "collection",
                "collection_id": collection["id"],
            }
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["scope"]["scope_type"] == "collection"
    assert data["artifact_summary"]["member_count"] == 1
    assert "actions" in data


def test_scope_artifacts_folder(client, sample_osii_object):
    folder_id = sample_osii_object["root_folder_id"]

    response = client.post(
        "/api/scopes/artifacts",
        json={
            "scope": {
                "scope_type": "folder",
                "folder_id": folder_id,
            }
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["scope"]["scope_type"] == "folder"
    assert "artifact_summary" in data
    assert "actions" in data