def test_scopes_root_endpoint(client, sample_osii_object):
    response = client.get("/api/scopes/root")
    assert response.status_code == 200
    data = response.json()
    assert data["scope"]["scope_type"] == "root"
    assert sample_osii_object["file_id"] in data["member_file_ids"]


def test_scopes_folders_endpoint(client, sample_osii_object):
    response = client.get("/api/scopes/folders")
    assert response.status_code == 200
    data = response.json()
    assert "scopes" in data
    assert any(item["folder_id"] == sample_osii_object["root_folder_id"] for item in data["scopes"])


def test_scopes_collections_endpoint(client, temp_osii_root):
    from osii.domain.scopes.collections import create_collection

    create_collection(
        temp_osii_root,
        name="api-collection",
        description="test",
        kind="manual",
        color=None,
    )

    response = client.get("/api/scopes/collections")
    assert response.status_code == 200
    data = response.json()
    assert "scopes" in data
    assert any(item["label"] == "api-collection" for item in data["scopes"])


def test_scopes_describe_endpoint(client, sample_osii_object):
    response = client.post(
        "/api/scopes/describe",
        json={"scope_type": "object", "file_id": sample_osii_object["file_id"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["scope"]["scope_type"] == "object"
    assert data["member_file_ids"] == [sample_osii_object["file_id"]]