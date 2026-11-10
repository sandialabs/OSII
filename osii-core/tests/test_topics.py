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


@pytest.mark.parametrize("payload", [{"limit": -1}, {"scope": {"scope_type": "unknown"}}, {"scope": {"scope_type": "folder"}}, {"limit": 0}])
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


def test_cached_map_skips_faiss_and_refreshes_synthesis_metadata(client, topic_index, monkeypatch):
    from osii.domain.storage.objects import update_synthesis_provenance
    first=client.post('/api/topics/map',json={}).json()
    monkeypatch.setattr(topics.faiss,'read_index',lambda _:pytest.fail('Cached map must not reload the vector index'))
    assert client.post('/api/topics/map',json={}).json()==first
    update_synthesis_provenance(topic_index,'a',synthesizer_name='test',synthesizer_version='1',config={
        'document_metadata':{'schema_version':1,'method':'text_llm',
            'title':{'value':'Kitchen Garden Guide'},'author':{'qualifier':'Not identified'},'date':{'value':'circa 1940s'}}})
    second=client.post('/api/topics/map',json={}).json()
    assert second['points'][0]['document_title']=='Kitchen Garden Guide'
    assert second['points'][0]['document_metadata']['author']['value'] is None
    assert [(p['x'],p['y']) for p in second['points']]==[(p['x'],p['y']) for p in first['points']]
    mark_artifacts_stale(topic_index,'a',syntheses=True)
    assert client.post('/api/topics/map',json={}).json()['points'][0]['document_metadata'] is None


def test_vector_and_scope_changes_invalidate_persisted_map(client, topic_index, monkeypatch):
    original=topics.faiss.read_index
    calls=[]
    def spy(path):
        calls.append(path);return original(path)
    monkeypatch.setattr(topics.faiss,'read_index',spy)
    client.post('/api/topics/map',json={});client.post('/api/topics/map',json={})
    assert len(calls)==1
    path=embeddings_mapping_path(topic_index)
    path.write_text(path.read_text().replace('"file_id": "d"','"file_id": "deleted"'))
    assert client.post('/api/topics/map',json={}).json()['indexed_count']==3
    assert len(calls)==2
    assert client.post('/api/topics/map',json={'scope':{'scope_type':'object','file_id':'a'}}).json()['shown_count']==1
    assert len(calls)==3


def test_corrupt_cached_geometry_is_rebuilt_without_touching_sources(client, topic_index):
    client.post('/api/topics/map',json={})
    cache=next((topic_index/'cache/topics').glob('*.json'))
    cache.write_text('{"projection":"pca","points":[{"x":"not-a-number"}]}')
    assert client.post('/api/topics/map',json={}).status_code==200
    assert (topic_index/'objects/a/meta.toml').is_file()


def test_large_projection_uses_bounded_subspace_and_preserves_dominant_structure(monkeypatch):
    from osii.domain import topic_projection
    rng = np.random.default_rng(13)
    vectors = (rng.normal(size=(4096, 2)) @ rng.normal(size=(2, 128)) + rng.normal(scale=.002, size=(4096, 128))).astype(np.float32)
    svd = np.linalg.svd
    shapes = []
    def bounded_svd(matrix, **kwargs):
        shapes.append(matrix.shape)
        assert min(matrix.shape) <= 12  # Never decompose the whole corpus.
        return svd(matrix, **kwargs)
    monkeypatch.setattr(topic_projection.np.linalg, "svd", bounded_svd)
    coordinates, variance = topic_projection.project_documents(vectors)
    again, _ = topic_projection.project_documents(vectors)
    assert coordinates.shape == (4096, 2) and np.isfinite(coordinates).all()
    assert np.array_equal(coordinates, again)
    assert .999 < variance <= 1
    centered = vectors - vectors.mean(axis=0)
    expected = svd(centered, full_matrices=False)[1][:2]
    assert np.allclose(np.linalg.svd(coordinates, compute_uv=False), expected, rtol=1e-4)
    assert len(shapes) == 3


def test_full_map_and_persisted_cache_cover_more_than_five_thousand_documents(client, topic_index, monkeypatch):
    from osii.domain.services import topic_cache
    count = 6001
    documents = [{"file_id": f"large-{i:05}", "source_relpath": f"large/{i}.pdf"} for i in range(count)]
    for module in (topics, topic_cache):
        monkeypatch.setattr(module, "load_files_catalog", lambda _: documents)
        monkeypatch.setattr(module, "list_scope_file_ids", lambda *_: [doc["file_id"] for doc in documents])
        monkeypatch.setattr(module, "get_artifact_staleness", lambda *_: {})
    monkeypatch.setattr(topic_cache, "get_suggested_metadata", lambda *_: {})
    vectors = np.random.default_rng(2).normal(size=(count, 64)).astype(np.float32)
    faiss.normalize_L2(vectors)
    index = faiss.IndexFlatIP(64); index.add(vectors)
    faiss.write_index(index, str(embeddings_index_path(topic_index)))
    embeddings_mapping_path(topic_index).write_text("".join(json.dumps({"faiss_id": i, "file_id": doc["file_id"]}) + "\n" for i, doc in enumerate(documents)))
    embeddings_meta_path(topic_index).write_text(tomli_w.dumps({"embeddings": {"count": count, "dimension": 64, "model": "osii-local-hashing-v1", "provider": "local.hashing", "semantic": False}}))
    response = client.post("/api/topics/map", json={})
    assert response.status_code == 200, response.text
    full = response.json()
    assert full["shown_count"] == full["indexed_count"] == count
    assert {point["file_id"] for point in full["points"]} == {doc["file_id"] for doc in documents}
    limited = client.post("/api/topics/map", json={"limit": 501}).json()
    assert limited["shown_count"] == 501
    assert limited["points"] == full["points"][:501]  # Limit affects output, never the fit.
    monkeypatch.setattr(topics.faiss, "read_index", lambda _: pytest.fail("Full cached map must skip vector loading"))
    assert client.post("/api/topics/map", json={}).json() == full


def test_large_identical_vectors_have_no_artificial_structure():
    coordinates, variance = topics.project_documents(np.full((6001, 64), .1, dtype=np.float32))
    assert not coordinates.any() and variance == 0


def test_vector_budget_returns_conflict_instead_of_a_partial_map(client, topic_index, monkeypatch):
    monkeypatch.setattr(topics, "MAX_DOCUMENT_VECTOR_BYTES", 1)
    response = client.post("/api/topics/map", json={})
    assert response.status_code == 409
    assert "document-vector limit" in response.json()["detail"]
