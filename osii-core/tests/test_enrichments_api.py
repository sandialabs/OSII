from osii.enrichment.stats_keywords import StatsKeywordsEnricher
from osii.domain.artifacts.enrichment_artifacts import write_collection_enrichment_variant
from osii.domain.scopes.collections import add_documents_to_collection, create_collection


def test_list_object_enrichments_api(client, temp_osii_root, sample_osii_object):
    file_id = sample_osii_object["file_id"]

    enricher = StatsKeywordsEnricher()
    enricher.enrich(
        osii_store=temp_osii_root,
        scope={"scope_type": "object", "file_id": file_id},
        enricher_config={"top_k": 10},
    )

    response = client.post(
        "/api/enrichments/list",
        json={"scope_type": "object", "file_id": file_id},
    )
    assert response.status_code == 200
    data = response.json()
    assert "enrichments" in data
    assert len(data["enrichments"]) >= 1


def test_get_object_enrichment_payload_api(client, temp_osii_root, sample_osii_object):
    file_id = sample_osii_object["file_id"]

    enricher = StatsKeywordsEnricher()
    enricher.enrich(
        osii_store=temp_osii_root,
        scope={"scope_type": "object", "file_id": file_id},
        enricher_config={"top_k": 10},
    )

    response = client.get(f"/api/enrichments/objects/{file_id}/keywords--stats_keywords.json")
    assert response.status_code == 200
    data = response.json()
    assert data["file_id"] == file_id
    assert data["filename"] == "keywords--stats_keywords.json"
    assert "keywords" in data["data"]
    assert data["data"]["artifact_type"] == "table"


def test_scope_enrichment_payload_endpoint(client, temp_osii_root, sample_osii_object):
    file_id = sample_osii_object["file_id"]
    StatsKeywordsEnricher().enrich(
        osii_store=temp_osii_root,
        scope={"scope_type": "object", "file_id": file_id},
        enricher_config={"top_k": 10},
    )

    response = client.post(
        "/api/enrichments/payload",
        json={
            "scope": {"scope_type": "object", "file_id": file_id},
            "filename": "keywords--stats_keywords.json",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["scope_type"] == "object"
    assert data["data"]["artifact_type"] == "table"


def test_delete_collection_wiki_removes_only_artifact_and_metadata(client, temp_osii_root, sample_osii_object):
    collection = create_collection(temp_osii_root, name="Wiki demo")
    add_documents_to_collection(temp_osii_root, collection["id"], [sample_osii_object["file_id"]])
    paths = write_collection_enrichment_variant(
        temp_osii_root,
        collection["id"],
        kind="wiki",
        method="llm_wiki",
        payload={"artifact_type": "wiki_markdown", "markdown": "# Demo"},
        metadata={"provider": "test"},
    )
    response = client.request(
        "DELETE",
        "/api/enrichments/payload",
        json={
            "scope": {"scope_type": "collection", "collection_id": collection["id"]},
            "filename": "wiki--llm_wiki.json",
        },
    )
    assert response.status_code == 200
    assert response.json()["metadata_deleted"] is True
    assert not (temp_osii_root / paths["data_path"]).exists()
    assert not (temp_osii_root / paths["metadata_path"]).exists()
    assert (temp_osii_root / "collections" / collection["id"] / "collection.toml").exists()
    second = client.request(
        "DELETE",
        "/api/enrichments/payload",
        json={
            "scope": {"scope_type": "collection", "collection_id": collection["id"]},
            "filename": "wiki--llm_wiki.json",
        },
    )
    assert second.status_code == 404
