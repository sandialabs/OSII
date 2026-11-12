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


def test_scope_overview_reports_recorded_metadata_not_invented_dates(client, sample_osii_object):
    response = client.post("/api/scopes/overview", json={"scope": {"scope_type": "root"}})
    assert response.status_code == 200
    data = response.json()
    assert data["file_count"] == data["size_known_count"] == 1
    assert data["average_size_bytes"] == data["total_size_bytes"] == 1234
    assert data["file_types"] == [{"label": ".pdf", "count": 1}]
    assert data["dates"]["created"]["recorded_count"] == 0
    assert data["dates"]["created"]["missing_count"] == 1
    assert data["dates"]["modified"]["buckets"] == [{"label": "2026-05", "count": 1}]
    assert data["processing"]["text_count"] == 1
    assert data["processing"]["indexed_count"] == 0
    assert data["processing"]["semantic_index"]["status"] == "missing"


def test_overview_does_not_create_missing_artifact_directories(client, temp_osii_root, sample_osii_object):
    from osii.domain.catalog_db import ensure_catalog

    ensure_catalog(temp_osii_root)
    before = {path.relative_to(temp_osii_root) for path in temp_osii_root.rglob("*")}
    response = client.post("/api/scopes/overview", json={"scope_type": "root"})
    assert response.status_code == 200
    assert {path.relative_to(temp_osii_root) for path in temp_osii_root.rglob("*")} == before


def test_overview_respects_named_collection_membership(client, temp_osii_root, sample_osii_object):
    from osii.domain.scopes.collections import add_documents_to_collection, create_collection

    collection = create_collection(temp_osii_root, name="Selected reports")
    scope = {"scope_type": "collection", "collection_id": collection["id"]}
    assert client.post("/api/scopes/overview", json=scope).json()["file_count"] == 0
    add_documents_to_collection(temp_osii_root, collection["id"], [sample_osii_object["file_id"]])
    assert client.post("/api/scopes/overview", json=scope).json()["file_count"] == 1


def test_overview_excludes_missing_sizes_but_keeps_zero_and_missing_members(temp_osii_root, monkeypatch):
    from osii.domain.scopes import overview

    metadata = {"zero": {"file": {"filename": r"C:\reports\empty.PDF", "size_bytes": 0}},
                "known": {"file": {"filename": "report.txt", "size_bytes": 100}},
                "unknown": None}
    monkeypatch.setattr(overview, "list_scope_file_ids", lambda *_: ["zero", "known", "unknown", "zero"])
    monkeypatch.setattr(overview, "get_doc_meta", lambda _, file_id: metadata[file_id])
    data = overview.get_scope_overview(temp_osii_root, {"scope_type": "root"})
    assert data["file_count"] == 3
    assert data["size_known_count"] == 2
    assert data["average_size_bytes"] == 50
    assert data["missing_metadata_count"] == 1
    assert {item["label"] for item in data["file_types"]} == {".pdf", ".txt", "No extension / unknown"}
    assert data["dates"]["created"]["missing_count"] == 3


def test_date_histogram_keeps_gaps_and_bounds_long_histories():
    from datetime import UTC, datetime
    from osii.domain.scopes.overview import _date_histogram, _recorded_date

    dates = [datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 3, 1, tzinfo=UTC)]
    assert _date_histogram(dates, 3)["buckets"] == [
        {"label": "2026-01", "count": 1}, {"label": "2026-02", "count": 0},
        {"label": "2026-03", "count": 1},
    ]
    long = _date_histogram([datetime(1900, 1, 1, tzinfo=UTC), *dates], 4)
    assert len(long["buckets"]) <= 12
    assert sum(item["count"] for item in long["buckets"]) == 3
    assert long["missing_count"] == 1
    assert _recorded_date("not a date") is None
    assert _recorded_date("2026-01-01T01:00:00+01:00").hour == 0


def test_overview_validates_selected_index_and_rejects_stale_or_inconsistent_vectors(
    client, temp_osii_root, sample_osii_object,
):
    import json
    import faiss
    import numpy as np
    import tomli_w
    from osii.domain.artifacts.artifact_staleness import mark_artifacts_stale
    from osii.domain.model_provider_config import selected_model, selected_processor
    from osii.indexing.common import embedding_namespace

    provider = selected_processor("embedder", osii_root=temp_osii_root)
    model = selected_model("embedder", osii_root=temp_osii_root)
    directory = temp_osii_root / "embeddings" / "providers"
    provider_dir, model_dir = embedding_namespace(model=model, provider=provider)
    directory = directory / provider_dir / model_dir
    directory.mkdir(parents=True)
    index = faiss.IndexFlatIP(3)
    index.add(np.array([[1, 0, 0]], dtype="float32"))
    faiss.write_index(index, str(directory / "segments.faiss"))
    mapping = directory / "segments.mapping.jsonl"
    mapping.write_text(json.dumps({"faiss_id": 0, "file_id": sample_osii_object["file_id"]}) + "\n")
    meta = {"embeddings": {"semantic": True, "provider": provider, "model": model, "dimension": 3, "count": 1}}
    meta_path = directory / "segments.meta.toml"
    meta_path.write_text(tomli_w.dumps(meta))
    scope = {"scope_type": "root"}
    data = client.post("/api/scopes/overview", json=scope).json()
    assert data["processing"]["indexed_count"] == 1
    assert data["processing"]["semantic_index"]["status"] == "ready"

    mark_artifacts_stale(temp_osii_root, sample_osii_object["file_id"], embeddings=True)
    assert client.post("/api/scopes/overview", json=scope).json()["processing"]["indexed_count"] == 0
    mapping.write_text(json.dumps({"faiss_id": 10, "file_id": sample_osii_object["file_id"]}) + "\n")
    assert client.post("/api/scopes/overview", json=scope).json()["processing"]["semantic_index"]["status"] == "invalid"
    meta["embeddings"]["semantic"] = False
    meta_path.write_text(tomli_w.dumps(meta))
    assert client.post("/api/scopes/overview", json=scope).json()["processing"]["semantic_index"]["status"] == "incompatible"


def test_overview_empty_edits_and_corrupt_metadata_are_not_completed_reading(
    client, temp_osii_root, sample_osii_object,
):
    from osii.domain.artifacts.edited_text import put_edited_text_segments

    file_id = sample_osii_object["file_id"]
    scope = {"scope_type": "object", "file_id": file_id}
    put_edited_text_segments(temp_osii_root, file_id, [{"id": "seg-000001", "text": ""}])
    assert client.post("/api/scopes/overview", json=scope).json()["processing"]["text_count"] == 0
    (temp_osii_root / "objects" / file_id / "meta.toml").write_text("[file\ninvalid")
    data = client.post("/api/scopes/overview", json=scope).json()
    assert data["file_count"] == 1
    assert len(data["warnings"]) == 1
    assert data["average_size_bytes"] is None
    assert client.post("/api/scopes/overview", json={"scope_type": "unsupported"}).status_code == 400


def test_overview_does_not_follow_an_object_outside_the_store(temp_osii_root, monkeypatch):
    from osii.domain.scopes import overview

    monkeypatch.setattr(overview, "list_scope_file_ids", lambda *_: ["../../outside"])
    monkeypatch.setattr(overview, "get_doc_meta", lambda *_: (_ for _ in ()).throw(AssertionError("Must not read outside")))
    data = overview.get_scope_overview(temp_osii_root, {"scope_type": "root"})
    assert data["missing_metadata_count"] == 1
    assert data["processing"]["text_count"] == 0
