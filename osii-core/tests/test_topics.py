import json

import faiss
import numpy as np
import pytest
import tomli_w

from osii.domain.artifacts.artifact_staleness import mark_artifacts_stale
from osii.domain.catalog_db import rebuild_catalog
from osii.domain.scopes.collections import add_documents_to_collection, create_collection
from osii.domain.services import topics
from osii.domain.storage.objects import write_meta_toml, write_provenance_toml
from osii.indexing.common import embeddings_index_path, embeddings_mapping_path, embeddings_meta_path


@pytest.fixture
def topic_index(temp_osii_root):
    documents = [("a", "source/reports/alpha.pdf"), ("b", "source/reports/beta.pdf"),
                 ("c", "source/other/gamma.pdf"), ("d", "source/other/delta.pdf")]
    for file_id, path in documents:
        write_meta_toml(temp_osii_root, file_id, path, path.split("/")[-1], "application/pdf", 10, "2026-11-04T00:00:00Z", file_id)
        write_provenance_toml(temp_osii_root, file_id, "test", status="done", extractor_name="test", extractor_version="1")
    rebuild_catalog(temp_osii_root)
    vectors = np.array([[1, 0, 0], [1, 0, 0], [0.9, 0.1, 0], [-1, 0, 0], [0, 1, 0]], dtype="float32")
    faiss.normalize_L2(vectors)
    index = faiss.IndexFlatIP(3)
    index.add(vectors)
    faiss.write_index(index, str(embeddings_index_path(temp_osii_root)))
    embeddings_mapping_path(temp_osii_root).write_text("".join(
        json.dumps({"faiss_id": i, "file_id": file_id}) + "\n"
        for i, file_id in enumerate(["a", "a", "b", "c", "d"])
    ))
    embeddings_meta_path(temp_osii_root).write_text(tomli_w.dumps({"embeddings": {
        "count": 5, "dimension": 3, "model": "osii-local-hashing-v1", "provider": "local.hashing", "semantic": False,
    }}))
    return temp_osii_root


def test_map_aggregates_documents_and_discloses_subset(client, topic_index):
    response = client.post("/api/topics/map", json={"limit": 2})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["indexed_count"] == data["scope_count"] == 4
    assert data["shown_count"] == 2
    assert data["index"]["semantic"] is False
    assert data["points"][0]["chunk_count"] == 2
    assert {p["file_id"] for p in data["points"]} == {"a", "b"}
    assert 0 <= data["explained_variance"] <= 1.000001
    assert client.post("/api/topics/map", json={"limit": 2}).json() == data


def test_related_uses_full_space_not_2d_or_map_subset(client, topic_index):
    data = client.post("/api/topics/related", json={"file_id": "a"}).json()
    assert [p["file_id"] for p in data["results"]] == ["b", "d", "c"]
    assert data["results"][0]["similarity"] == pytest.approx(0.9938837)
    assert data["results"][-1]["similarity"] == pytest.approx(-1)
    assert data["document"]["chunk_count"] == 2


def test_collection_scope_cannot_leak_other_documents(client, topic_index):
    collection = create_collection(topic_index, name="Only two")
    add_documents_to_collection(topic_index, collection["id"], ["a", "d"])
    scope = {"scope_type": "collection", "collection_id": collection["id"]}
    data = client.post("/api/topics/map", json={"scope": scope}).json()
    assert {p["file_id"] for p in data["points"]} == {"a", "d"}
    data = client.post("/api/topics/related", json={"scope": scope, "file_id": "a"}).json()
    assert [p["file_id"] for p in data["results"]] == ["d"]
    assert client.post("/api/topics/related", json={"scope": scope, "file_id": "b"}).status_code == 409
    for scope in ({"scope_type": "folder", "folder_id": "missing"}, {"scope_type": "collection", "collection_id": "missing"}):
        assert client.post("/api/topics/map", json={"scope": scope}).json()["points"] == []


def test_stale_and_deleted_documents_are_excluded(client, topic_index):
    mark_artifacts_stale(topic_index, "b", embeddings=True)
    (topic_index / "objects" / "c" / "meta.toml").unlink()
    rebuild_catalog(topic_index)
    data = client.post("/api/topics/map", json={}).json()
    assert {p["file_id"] for p in data["points"]} == {"a", "d"}
    assert data["stale_count"] == 1
    assert data["scope_count"] == 3


def test_folder_and_object_scope_and_unindexed_counts(client, topic_index):
    from osii.domain.storage.folders import write_folder_manifest

    write_folder_manifest(topic_index, folder_id="folder-reports", path_hint="reports",
                          docs=[{"file_id": "a", "source_relpath": "source/reports/alpha.pdf"},
                                {"file_id": "b", "source_relpath": "source/reports/beta.pdf"}],
                          subfolders=[], stats={"file_count": 2}, entrypoints=None)
    rebuild_catalog(topic_index)
    scope = {"scope_type": "folder", "folder_id": "folder-reports"}
    data = client.post("/api/topics/map", json={"scope": scope}).json()
    assert {p["file_id"] for p in data["points"]} == {"a", "b"}
    data = client.post("/api/topics/related", json={"scope": scope, "file_id": "a"}).json()
    assert [p["file_id"] for p in data["results"]] == ["b"]
    scope = {"scope_type": "object", "file_id": "a"}
    assert client.post("/api/topics/map", json={"scope": scope}).json()["shown_count"] == 1
    assert client.post("/api/topics/related", json={"scope": scope, "file_id": "a"}).json()["results"] == []
    path = embeddings_mapping_path(topic_index)
    path.write_text(path.read_text().replace('"file_id": "b"', '"file_id": "deleted"'))
    assert client.post("/api/topics/map", json={}).json()["unindexed_count"] == 1


@pytest.mark.parametrize("failure", ["missing", "truncated", "wrong-id", "dimensions", "nan", "other-model", "changing"])
def test_invalid_indexes_return_actionable_conflict(client, topic_index, monkeypatch, failure):
    if failure == "missing":
        embeddings_index_path(topic_index).unlink()
    elif failure == "truncated":
        embeddings_mapping_path(topic_index).write_text('{"file_id":"a"}\n')
    elif failure == "wrong-id":
        path = embeddings_mapping_path(topic_index)
        path.write_text(path.read_text().replace('"faiss_id": 0', '"faiss_id": 999'))
    elif failure == "dimensions":
        path = embeddings_meta_path(topic_index)
        path.write_text(path.read_text().replace('dimension = 3', 'dimension = 4'))
    elif failure == "nan":
        index = faiss.IndexFlatIP(3)
        index.add(np.full((5, 3), np.nan, dtype="float32"))
        faiss.write_index(index, str(embeddings_index_path(topic_index)))
    elif failure == "other-model":
        monkeypatch.setattr(topics, "embedding_namespace", lambda: ("different", "model"))
    else:
        read_index = topics.faiss.read_index
        def changing_index(path):
            index = read_index(path)
            meta = embeddings_meta_path(topic_index)
            meta.write_text(meta.read_text() + "\n# updated\n")
            return index
        monkeypatch.setattr(topics.faiss, "read_index", changing_index)
    response = client.post("/api/topics/map", json={})
    assert response.status_code == 409, response.text
    assert response.json()["detail"]


@pytest.mark.parametrize("payload", [{"limit": 501}, {"scope": {"scope_type": "unknown"}}, {"scope": {"scope_type": "folder"}}, {"limit": 0}])
def test_map_validates_requests(client, payload):
    assert client.post("/api/topics/map", json=payload).status_code == 422


@pytest.mark.parametrize("bound", ["MAX_INDEX_BYTES", "MAX_MAPPING_BYTES"])
def test_oversized_indexes_are_rejected_before_allocating_vectors(client, topic_index, monkeypatch, bound):
    monkeypatch.setattr(topics, bound, 1)

    def must_not_load(_path):
        raise AssertionError("Oversized indexes must be rejected before FAISS allocation")

    monkeypatch.setattr(topics.faiss, "read_index", must_not_load)
    response = client.post("/api/topics/map", json={})
    assert response.status_code == 409
    assert "limits" in response.json()["detail"]


def test_degenerate_projection_has_finite_coordinates():
    for vectors in (np.empty((0, 3)), np.ones((1, 3)), np.ones((3, 3))):
        coordinates, variance = topics.project_documents(vectors)
        assert coordinates.shape == (len(vectors), 2)
        assert np.isfinite(coordinates).all()
        assert variance == 0
