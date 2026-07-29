from pathlib import Path

from osii.domain.scopes.collection_files import (
    load_collection_definition,
    parse_collection_metadata,
    resolve_collection_members,
)


def test_parse_collection_metadata():
    payload = {
        "collection": {
            "name": "thermal-set",
            "description": "Collection for thermal docs",
            "kind": "file-list",
            "color": "#3366ff",
        }
    }

    data = parse_collection_metadata(payload)
    assert data["name"] == "thermal-set"
    assert data["description"] == "Collection for thermal docs"
    assert data["kind"] == "file-list"
    assert data["color"] == "#3366ff"


def test_resolve_collection_members_by_file_id(temp_osii_root, sample_osii_object):
    file_id = sample_osii_object["file_id"]

    payload = {
        "members": [
            {"file_id": file_id},
        ]
    }

    result = resolve_collection_members(temp_osii_root, payload)
    assert result == [file_id]


def test_resolve_collection_members_by_source_relpath(temp_osii_root, sample_osii_object):
    payload = {
        "members": [
            {"source_relpath": sample_osii_object["source_relpath"]},
        ]
    }

    result = resolve_collection_members(temp_osii_root, payload)
    assert result == [sample_osii_object["file_id"]]