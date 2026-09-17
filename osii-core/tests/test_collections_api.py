def test_collections_crud_api(client):
    create_resp = client.post(
        "/api/collections",
        json={"name": "favorites", "description": "favorite docs", "kind": "manual", "color": "#3333ff"},
    )
    assert create_resp.status_code == 200
    collection = create_resp.json()["collection"]
    collection_id = collection["id"]

    list_resp = client.get("/api/collections")
    assert list_resp.status_code == 200
    assert any(c["id"] == collection_id for c in list_resp.json()["collections"])

    get_resp = client.get(f"/api/collections/{collection_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["collection"]["name"] == "favorites"

    patch_resp = client.patch(
        f"/api/collections/{collection_id}",
        json={"name": "favorites-updated", "kind": "manual"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["collection"]["name"] == "favorites-updated"

    del_resp = client.delete(f"/api/collections/{collection_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["ok"] is True


def test_collection_members_api(client, sample_osii_object):
    file_id = sample_osii_object["file_id"]

    create_resp = client.post(
        "/api/collections",
        json={"name": "calibration", "description": "docs", "kind": "manual", "color": None},
    )
    collection_id = create_resp.json()["collection"]["id"]

    add_resp = client.post(
        f"/api/collections/{collection_id}/members",
        json={"file_ids": [file_id]},
    )
    assert add_resp.status_code == 200
    assert add_resp.json()["added"] == [file_id]

    list_resp = client.get(f"/api/collections/{collection_id}/members")
    assert list_resp.status_code == 200
    assert file_id in list_resp.json()["file_ids"]

    remove_resp = client.delete(f"/api/collections/{collection_id}/members/{file_id}")
    assert remove_resp.status_code == 200
    assert remove_resp.json()["removed"] is True


def test_collection_export_contains_only_selected_sidecar(client, sample_osii_object):
    import io
    import zipfile

    file_id = sample_osii_object["file_id"]
    collection_id = client.post("/api/collections", json={"name": "shareable"}).json()["collection"]["id"]
    client.post(f"/api/collections/{collection_id}/members", json={"file_ids": [file_id]})

    response = client.get(f"/api/collections/{collection_id}/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
    assert f"collections/{collection_id}/collection.toml" in names
    assert f"objects/{file_id}/meta.toml" in names
    assert not any(name.startswith("source/") for name in names)
