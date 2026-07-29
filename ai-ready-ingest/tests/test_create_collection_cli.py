from osii.domain.scopes.collections import get_collection, list_collection_documents
from osii.create_collection import find_collection_by_name
from osii.domain.scopes.collection_files import (
    parse_collection_metadata,
    resolve_collection_members,
)
from osii.domain.scopes.collections import create_collection, add_documents_to_collection


def test_create_collection_flow_from_payload(temp_osii_root, sample_osii_object):
    payload = {
        "collection": {
            "name": "thermal-set",
            "description": "Collection for thermal docs",
            "kind": "file-list",
            "color": None,
        },
        "members": [
            {"source_relpath": sample_osii_object["source_relpath"]},
        ],
    }

    metadata = parse_collection_metadata(payload)
    file_ids = resolve_collection_members(temp_osii_root, payload)

    collection = create_collection(
        temp_osii_root,
        name=metadata["name"],
        description=metadata["description"],
        kind=metadata["kind"],
        color=metadata["color"],
    )

    add_documents_to_collection(temp_osii_root, collection["id"], file_ids)

    stored = get_collection(temp_osii_root, collection["id"])
    assert stored is not None
    assert stored["name"] == "thermal-set"
    assert stored["kind"] == "file-list"

    members = list_collection_documents(temp_osii_root, collection["id"])
    assert members == [sample_osii_object["file_id"]]