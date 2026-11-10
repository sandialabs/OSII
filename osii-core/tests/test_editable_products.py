"""Human changes survive regeneration; stale writes cannot replace newer edits."""

import json

import pytest
from osii.domain.artifacts.products import (
    edit_product_data,
    product_path,
    publish_product,
    read_product,
    write_text_product,
)
from osii.domain.document_metadata import METADATA_FIELDS
from osii.domain.read.synthesis import get_synth_text, get_suggested_metadata
from osii.domain.storage.store import object_synth_path
from osii.processor_sdk import DocumentMetadata


def test_summary_edit_regeneration_and_history_api(
    client, temp_osii_root, sample_osii_object
):
    fid = sample_osii_object["file_id"]
    address = {
        "scope": {"scope_type": "object", "file_id": fid},
        "family": "synthesis",
        "filename": "current",
    }
    before = client.post("/api/products/revisions", json=address).json()
    changed = client.put(
        "/api/products/revisions",
        json={
            **address,
            "expected_revision": before["current"],
            "data": {"text": "Human summary $E=mc^2$"},
        },
    )
    assert changed.status_code == 200
    current = changed.json()["current"]
    assert (
        client.put(
            "/api/products/revisions",
            json={
                **address,
                "expected_revision": before["current"],
                "data": {"text": "Lost edit"},
            },
        ).status_code
        == 409
    )
    write_text_product(
        temp_osii_root, object_synth_path(temp_osii_root, fid), "New generated summary"
    )
    assert get_synth_text(temp_osii_root, fid) == "Human summary $E=mc^2$"
    history = client.post("/api/products/revisions", json=address).json()
    assert history["current"] == current
    assert history["revisions"][-1]["data"]["text"] == "New generated summary"
    restored = client.put(
        "/api/products/revisions",
        json={
            **address,
            "expected_revision": current,
            "revision": history["revisions"][-1]["id"],
        },
    )
    assert restored.status_code == 200
    assert get_synth_text(temp_osii_root, fid) == "New generated summary"
    assert (
        client.get(f"/api/objects/{fid}/syntheses").json()["current_text"]
        == "New generated summary"
    )
    assert any(
        item["family"] == "synthesis"
        for item in client.post("/api/products/list", json=address["scope"]).json()[
            "products"
        ]
    )


@pytest.mark.parametrize(
    "scope,filename",
    [
        ({"scope_type": "folder", "folder_id": "f"}, "current"),
        ({"scope_type": "root"}, "current"),
        ({"scope_type": "collection", "collection_id": "c"}, "summary.txt"),
    ],
)
def test_scope_summary_edit(temp_osii_root, scope, filename):
    path = product_path(temp_osii_root, scope, filename, "synthesis")
    write_text_product(temp_osii_root, path, "Generated")
    previous = read_product(path)["current"]
    edit_product_data(
        temp_osii_root, scope, filename, {"text": "Human"}, previous, "synthesis"
    )
    write_text_product(temp_osii_root, path, "Regenerated")
    assert path.read_text() == "Human"


def test_structured_products_validate_format_and_preserve_original(
    client, temp_osii_root, sample_osii_object
):
    scope = {"scope_type": "object", "file_id": sample_osii_object["file_id"]}
    path = product_path(temp_osii_root, scope, "table.json")
    data = {
        "artifact_type": "table",
        "title": "Counts",
        "columns": [{"key": "count", "label": "Count"}],
        "rows": [{"count": 2}],
    }
    publish_product(temp_osii_root, path, data)
    original = read_product(path)
    address = {
        "scope": scope,
        "filename": "table.json",
        "expected_revision": original["current"],
    }
    invalid = client.put(
        "/api/products/revisions",
        json={**address, "data": {**data, "artifact_type": "entity_list"}},
    )
    assert invalid.status_code == 400
    result = client.put(
        "/api/products/revisions",
        json={**address, "data": {**data, "rows": [{"count": 3}]}},
    )
    assert result.status_code == 200
    publish_product(temp_osii_root, path, {**data, "rows": [{"count": 4}]})
    assert read_product(path)["data"]["rows"] == [{"count": 3}]
    assert read_product(path)["revisions"][0]["data"] == data
    assert json.loads(path.read_text())["rows"] == [{"count": 3}]


def test_metadata_all_fields_blank_distinct_titles_and_conflict(
    client, temp_osii_root, sample_osii_object
):
    fid = sample_osii_object["file_id"]
    endpoint = f"/api/objects/{fid}/metadata"
    assert client.get(endpoint).json()["revision"] is None
    values = {name: "" for name in METADATA_FIELDS}
    values.update(
        descriptive_title="Thermal drift experiment",
        title="Report 123",
        agency="National lab",
        document_type="Technical report",
    )
    response = client.put(endpoint, json={"values": values, "expected_revision": None})
    assert response.status_code == 200
    metadata = DocumentMetadata.model_validate(response.json()["document_metadata"])
    assert metadata.descriptive_title.value != metadata.title.value
    assert metadata.author.value is None and metadata.date.value is None
    assert metadata.method == "human"
    assert (
        get_suggested_metadata(temp_osii_root, fid)["document_title"]
        == "Thermal drift experiment"
    )
    assert (
        client.put(
            endpoint, json={"values": values, "expected_revision": None}
        ).status_code
        == 409
    )
    assert client.put(endpoint, json={"values": values}).status_code == 400
    assert (
        client.get(f"/api/objects/{fid}/syntheses").json()["document_metadata"][
            "agency"
        ]["value"]
        == "National lab"
    )
    assert (
        client.put(
            endpoint,
            json={
                "values": {name: " " for name in METADATA_FIELDS},
                "expected_revision": response.json()["revision"],
            },
        ).status_code
        == 200
    )
    assert get_suggested_metadata(temp_osii_root, fid)["document_title"] is None


def test_old_metadata_contract_defaults_new_fields():
    record = DocumentMetadata.model_validate(
        {"title": {"value": "Title"}, "author": {}, "date": {}}
    )
    assert all(
        getattr(record, key).value is None
        for key in ("descriptive_title", "agency", "document_type")
    )


def test_extraction_editable_copy_is_separate_and_idempotent(
    client, temp_osii_root, sample_osii_object
):
    fid = sample_osii_object["file_id"]
    state = client.get(f"/api/objects/{fid}/extractions").json()
    variant = state["primary_id"]
    endpoint = f"/api/objects/{fid}/extractions/{variant}/editable-copy"
    address = client.post(endpoint, json={}).json()
    before = client.post("/api/products/revisions", json=address).json()
    assert (
        client.put(
            "/api/products/revisions",
            json={
                **address,
                "expected_revision": before["current"],
                "data": {"artifact_type": "text", "text": "Corrected copy"},
            },
        ).status_code
        == 200
    )
    assert client.post(endpoint, json={}).json() == address
    assert (
        client.post("/api/products/revisions", json=address).json()["data"]["text"]
        == "Corrected copy"
    )
    assert (
        temp_osii_root / "objects" / fid / "text.txt"
    ).read_text() == "Thermal calibration drift was reduced."
    assert client.get(f"/api/objects/{fid}/extractions").json()["primary_id"] == variant
    assert (
        client.post(
            f"/api/objects/{fid}/extractions/not-registered/editable-copy", json={}
        ).status_code
        == 404
    )


def test_committed_summary_remains_discoverable_after_missing_mirror(
    client, temp_osii_root
):
    address = {
        "scope": {"scope_type": "root"},
        "family": "synthesis",
        "filename": "method.txt",
    }
    path = product_path(
        temp_osii_root, address["scope"], address["filename"], "synthesis"
    )
    write_text_product(temp_osii_root, path, "Committed summary")
    path.unlink()
    products = client.post("/api/products/list", json=address["scope"]).json()[
        "products"
    ]
    assert any(item["filename"] == "method.txt" for item in products)
    assert (
        client.post("/api/products/revisions", json=address).json()["data"]["text"]
        == "Committed summary"
    )


def test_products_list_excludes_internal_metadata(client, temp_osii_root):
    path = product_path(temp_osii_root, {"scope_type": "root"}, "table.json")
    publish_product(
        temp_osii_root,
        path,
        {"artifact_type": "table", "title": "Counts", "columns": [], "rows": []},
    )
    path.with_suffix(".meta.json").write_text('{"method":"test"}')
    response = client.post("/api/products/list", json={"scope_type": "root"})
    assert response.status_code == 200
    assert [item["filename"] for item in response.json()["products"]] == ["table.json"]


@pytest.mark.parametrize(
    "name,data",
    [
        ("legacy/summary.txt", {"text": "Edited plain text"}),
        (
            "legacy/wiki.md",
            {
                "artifact_type": "wiki_markdown",
                "title": "wiki",
                "markdown": "# Edited wiki",
                "citations": [],
            },
        ),
    ],
)
def test_legacy_bundle_text_can_be_edited(client, temp_osii_root, name, data):
    scope = {"scope_type": "root"}
    path = product_path(temp_osii_root, scope, name)
    path.parent.mkdir(exist_ok=True)
    path.write_text("Original content")
    address = {"scope": scope, "filename": name}
    before = client.post("/api/products/revisions", json=address).json()
    response = client.put(
        "/api/products/revisions",
        json={**address, "expected_revision": before["current"], "data": data},
    )
    assert response.status_code == 200
    assert path.read_text() == data.get("text", data.get("markdown"))
    assert len(response.json()["revisions"]) == 2
    assert any(
        item["filename"] == name
        for item in client.post("/api/products/list", json=scope).json()["products"]
    )


@pytest.mark.parametrize(
    "name",
    [
        "../outside.json",
        ".history/manifest.json",
        "/tmp/outside.txt",
        "legacy/../../outside.md",
        "legacy/meta.meta.json",
    ],
)
def test_product_paths_cannot_escape_scope(temp_osii_root, name):
    with pytest.raises(ValueError):
        product_path(temp_osii_root, {"scope_type": "root"}, name)


def test_markdown_mirror_does_not_invent_external_metadata_revision(temp_osii_root):
    scope = {"scope_type": "root"}
    path = product_path(temp_osii_root, scope, "wiki.md")
    publish_product(
        temp_osii_root,
        path,
        {
            "artifact_type": "wiki_markdown",
            "title": "Descriptive title",
            "markdown": "# Content",
            "citations": [],
        },
    )
    history = read_product(path)
    assert history["data"]["title"] == "Descriptive title"
    assert len(history["revisions"]) == 1
