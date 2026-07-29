from osii.domain.scopes.collections import create_collection, add_documents_to_collection
from osii.domain.scopes.membership import list_scope_file_ids


def test_list_scope_file_ids_root(temp_osii_root, sample_osii_object):
    result = list_scope_file_ids(
        temp_osii_root,
        {"scope_type": "root"},
    )
    assert sample_osii_object["file_id"] in result


def test_list_scope_file_ids_object(temp_osii_root, sample_osii_object):
    file_id = sample_osii_object["file_id"]
    result = list_scope_file_ids(
        temp_osii_root,
        {"scope_type": "object", "file_id": file_id},
    )
    assert result == [file_id]


def test_list_scope_file_ids_collection(temp_osii_root, sample_osii_object):
    file_id = sample_osii_object["file_id"]
    collection = create_collection(
        temp_osii_root,
        name="scope-test",
        description="test",
        kind="manual",
        color=None,
    )
    add_documents_to_collection(temp_osii_root, collection["id"], [file_id])

    result = list_scope_file_ids(
        temp_osii_root,
        {"scope_type": "collection", "collection_id": collection["id"]},
    )
    assert result == [file_id]