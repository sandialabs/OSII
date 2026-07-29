from osii.domain.artifacts.collection_artifacts import get_collection_artifact_summary


def test_collection_artifact_summary(temp_osii_root, sample_osii_object):
    from osii.domain.scopes.collections import create_collection, add_documents_to_collection

    file_id = sample_osii_object["file_id"]
    collection = create_collection(
        temp_osii_root,
        name="collection-artifacts-test",
        description="test",
        kind="manual",
        color=None,
    )
    add_documents_to_collection(temp_osii_root, collection["id"], [file_id])

    result = get_collection_artifact_summary(temp_osii_root, collection["id"])
    assert result is not None
    assert result["collection_id"] == collection["id"]
    assert result["artifacts"]["member_count"] == 1
    assert result["actions"]["can_synthesize"] is True
    assert result["actions"]["can_enrich"] is True