from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import zipfile


def test_structured_governance_is_canonical_sidecar_data(client, sample_osii_object, temp_osii_root):
    file_id = sample_osii_object["file_id"]
    response = client.put(
        f"/api/objects/{file_id}/governance",
        json={
            "sensitivity_labels": ["CUI", "PII", "cui"],
            "tags": ["export controlled", "Export Controlled"],
            "handling_notes": "Follow the local handling guide.",
        },
    )

    assert response.status_code == 200
    assert response.json()["governance"]["sensitivity_labels"] == ["CUI", "PII"]
    assert (temp_osii_root / "objects" / file_id / "governance.toml").exists()
    fetched = client.get(f"/api/objects/{file_id}/governance").json()["governance"]
    assert fetched["tags"] == ["export controlled"]


def test_collection_package_has_manifest_and_merges_labels_by_file_id(client, sample_osii_object):
    file_id = sample_osii_object["file_id"]
    client.put(
        f"/api/objects/{file_id}/governance",
        json={"sensitivity_labels": ["CUI"], "tags": ["Imported"], "handling_notes": "Incoming"},
    )
    collection_id = client.post("/api/collections", json={"name": "transfer"}).json()["collection"]["id"]
    client.post(f"/api/collections/{collection_id}/members", json={"file_ids": [file_id]})
    package = client.get(f"/api/collections/{collection_id}/export").content

    with zipfile.ZipFile(BytesIO(package)) as archive:
        manifest = json.loads(archive.read("osii-package.json"))
        assert manifest["format"] == "osii-sidecar-package"
        assert manifest["source_files_included"] is False
        assert any(item["path"] == f"objects/{file_id}/governance.toml" for item in manifest["files"])

    client.put(
        f"/api/objects/{file_id}/governance",
        json={"sensitivity_labels": ["PII"], "tags": ["Local"], "handling_notes": "Local"},
    )
    imported = client.post(
        "/api/packages/import",
        files={"package": ("transfer-osii-sidecar.zip", package, "application/zip")},
    )

    assert imported.status_code == 200
    assert imported.json()["duplicate_file_ids"] == [file_id]
    assert imported.json()["governance_merged_file_ids"] == [file_id]
    merged = client.get(f"/api/objects/{file_id}/governance").json()["governance"]
    assert merged["sensitivity_labels"] == ["PII", "CUI"]
    assert merged["tags"] == ["Local", "Imported"]


def test_package_rejects_content_that_does_not_match_manifest(client, sample_osii_object):
    file_id = sample_osii_object["file_id"]
    collection_id = client.post("/api/collections", json={"name": "checksums"}).json()["collection"]["id"]
    client.post(f"/api/collections/{collection_id}/members", json={"file_ids": [file_id]})
    package = client.get(f"/api/collections/{collection_id}/export").content
    source = zipfile.ZipFile(BytesIO(package))
    output = BytesIO()
    with source, zipfile.ZipFile(output, "w") as altered:
        for info in source.infolist():
            content = source.read(info.filename)
            if info.filename.endswith("/meta.toml"):
                content += b"\n# altered"
            altered.writestr(info.filename, content)

    response = client.post(
        "/api/packages/import",
        files={"package": ("altered.zip", output.getvalue(), "application/zip")},
    )
    assert response.status_code == 400
    assert "checksum" in response.json()["detail"].lower()


def test_previewed_sidecar_deletion_keeps_source_and_invalidates_derived_data(
    client,
    sample_osii_object,
    temp_data_root: Path,
    temp_osii_root: Path,
):
    file_id = sample_osii_object["file_id"]
    source = temp_data_root / "example_data" / "purcell.pdf"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"source")
    collection_id = client.post("/api/collections", json={"name": "sensitive"}).json()["collection"]["id"]
    client.post(f"/api/collections/{collection_id}/members", json={"file_ids": [file_id]})
    (temp_osii_root / "root.synth.txt").write_text("derived excerpt", encoding="utf-8")
    embeddings = temp_osii_root / "embeddings" / "providers" / "test"
    embeddings.mkdir(parents=True, exist_ok=True)
    (embeddings / "segments.faiss").write_bytes(b"index")

    preview = client.post(
        f"/api/objects/{file_id}/deletion-preview",
        json={"mode": "sidecar_only"},
    )
    assert preview.status_code == 200
    impact = preview.json()
    assert impact["source_will_remain"] is True
    assert impact["collections"][0]["id"] == collection_id
    assert impact["indexes_rebuild_required"] is True

    deleted = client.request(
        "DELETE",
        f"/api/objects/{file_id}",
        json={
            "mode": "sidecar_only",
            "preview_token": impact["preview_token"],
            "confirmation": file_id,
        },
    )
    assert deleted.status_code == 200
    assert source.exists()
    assert not (temp_osii_root / "objects" / file_id).exists()
    assert not (temp_osii_root / "root.synth.txt").exists()
    assert list((temp_osii_root / "embeddings").iterdir()) == []
    members = client.get(f"/api/collections/{collection_id}/members").json()["file_ids"]
    assert file_id not in members
