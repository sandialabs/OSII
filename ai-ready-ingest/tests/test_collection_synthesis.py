def test_collection_syntheses_endpoint(client, temp_osii_root, sample_osii_object):
    from osii.domain.scopes.collections import create_collection, add_documents_to_collection
    from osii.synthesis.collection.firstn import CollectionFirstNSynthesizer

    file_id = sample_osii_object["file_id"]
    collection = create_collection(
        temp_osii_root,
        name="collection-synth-test",
        description="test",
        kind="manual",
        color=None,
    )
    add_documents_to_collection(temp_osii_root, collection["id"], [file_id])

    synthesizer = CollectionFirstNSynthesizer()
    synthesizer.synthesize_collection(
        osii_store=temp_osii_root,
        collection_id=collection["id"],
        expert_context=None,
        synthesizer_config={"max_chars": 100},
    )

    response = client.get(f"/api/collections/{collection['id']}/syntheses")
    assert response.status_code == 200
    data = response.json()
    assert data["collection"]["id"] == collection["id"]
    assert len(data["syntheses"]) >= 1


def test_collection_artifacts_endpoint(client, temp_osii_root, sample_osii_object):
    from osii.domain.scopes.collections import create_collection, add_documents_to_collection

    file_id = sample_osii_object["file_id"]
    collection = create_collection(
        temp_osii_root,
        name="collection-artifacts-endpoint-test",
        description="test",
        kind="manual",
        color=None,
    )
    add_documents_to_collection(temp_osii_root, collection["id"], [file_id])

    response = client.get(f"/api/collections/{collection['id']}/artifacts")
    assert response.status_code == 200
    data = response.json()
    assert data["collection_id"] == collection["id"]
    assert "artifacts" in data
    assert "actions" in data


def test_run_collection_synthesis_endpoint(client, monkeypatch, temp_osii_root, sample_osii_object):
    from osii.domain.scopes.collections import create_collection, add_documents_to_collection

    file_id = sample_osii_object["file_id"]
    collection = create_collection(
        temp_osii_root,
        name="collection-run-synth-test",
        description="test",
        kind="manual",
        color=None,
    )
    add_documents_to_collection(temp_osii_root, collection["id"], [file_id])

    class FakeCollectionSynthesizer:
        def synthesize_collection(
            self,
            *,
            osii_store,
            collection_id,
            expert_context=None,
            synthesizer_config=None,
        ):
            return {
                "scope_type": "collection",
                "collection_id": collection_id,
                "method": "collection_firstn",
                "text_path": f"collections/{collection_id}/syntheses/collection_firstn.txt",
                "metadata_path": f"collections/{collection_id}/syntheses/collection_firstn.json",
            }

    monkeypatch.setattr(
        "osii.api.collection_synthesis_routes.CollectionFirstNSynthesizer",
        FakeCollectionSynthesizer,
    )

    response = client.post(
        f"/api/collections/{collection['id']}/syntheses",
        json={
            "synthesizer_name": "collection_firstn",
            "synthesizer_config": {"max_chars": 100},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["collection_id"] == collection["id"]
    assert data["synthesizer_name"] == "collection_firstn"
    assert "run_id" in data