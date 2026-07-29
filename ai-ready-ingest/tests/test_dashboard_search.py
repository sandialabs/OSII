from osii.domain.services.search import dashboard_search
from osii.domain.scopes.collections import create_collection, add_documents_to_collection


def test_dashboard_search_lexical_root_scope(temp_osii_root, sample_osii_object):
    retrieval_mode, results = dashboard_search(
        temp_osii_root,
        query="thermal calibration drift",
        mode="lexical",
        top_k=5,
        scope={"scope_type": "root"},
    )
    assert retrieval_mode == "lexical"
    assert isinstance(results, list)
    assert len(results) >= 1
    assert results[0]["file_id"] == sample_osii_object["file_id"]
    assert results[0]["match_type"] in {"lexical", "hybrid"}


def test_dashboard_search_lexical_object_scope(temp_osii_root, sample_osii_object):
    file_id = sample_osii_object["file_id"]
    _, results = dashboard_search(
        temp_osii_root,
        query="thermal calibration drift",
        mode="lexical",
        top_k=5,
        scope={"scope_type": "object", "file_id": file_id},
    )
    assert isinstance(results, list)
    assert len(results) >= 1
    assert all(item["file_id"] == file_id for item in results)


def test_dashboard_search_lexical_collection_scope(temp_osii_root, sample_osii_object):
    file_id = sample_osii_object["file_id"]
    collection = create_collection(
        temp_osii_root,
        name="thermal-set",
        description="test",
        kind="manual",
        color=None,
    )
    add_documents_to_collection(temp_osii_root, collection["id"], [file_id])

    _, results = dashboard_search(
        temp_osii_root,
        query="thermal calibration drift",
        mode="lexical",
        top_k=5,
        scope={"scope_type": "collection", "collection_id": collection["id"]},
    )
    assert isinstance(results, list)
    assert len(results) >= 1
    assert all(item["file_id"] == file_id for item in results)


def test_dashboard_search_invalid_mode(temp_osii_root):
    try:
        dashboard_search(
            temp_osii_root,
            query="test",
            mode="nonsense",
            top_k=5,
            scope={"scope_type": "root"},
        )
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "Unsupported search mode" in str(exc)
