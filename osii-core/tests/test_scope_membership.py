from osii.domain.scopes.collections import create_collection, add_documents_to_collection
from osii.domain.scopes.membership import list_scope_file_ids
from osii.domain.storage.objects import write_meta_toml, write_provenance_toml
from osii.domain.storage.folders import write_folder_manifest


def test_list_scope_file_ids_root(temp_osii_root, sample_osii_object):
    result = list_scope_file_ids(
        temp_osii_root,
        {"scope_type": "root"},
    )
    assert sample_osii_object["file_id"] in result


def test_root_scope_publishes_each_completed_object_bundle(temp_osii_root):
    for file_id, status in (
        ("sha256-completed", "done"),
        ("sha256-still-running", "running"),
    ):
        write_meta_toml(
            temp_osii_root,
            file_id=file_id,
            source_relpath=f"my_data/{file_id}.txt",
            filename=f"{file_id}.txt",
            mime="text/plain",
            size_bytes=4,
            mtime_utc="2026-07-31T00:00:00+00:00",
            sha256_hex=file_id.removeprefix("sha256-"),
        )
        write_provenance_toml(
            temp_osii_root,
            file_id=file_id,
            pipeline_version="test",
            status=status,
            extractor_name="native_text",
            extractor_version="1.0",
        )

    result = list_scope_file_ids(temp_osii_root, {"scope_type": "root"})

    assert "sha256-completed" in result
    assert "sha256-still-running" not in result


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


def test_folder_scope_matches_current_and_legacy_source_namespaces(temp_osii_root):
    write_folder_manifest(
        temp_osii_root,
        folder_id="folder-reports",
        path_hint="reports",
        docs=[
            {"source_relpath": "my_data/reports/current.txt", "file_id": "file-current"},
            {"source_relpath": "source/reports/legacy.txt", "file_id": "file-legacy"},
            {"source_relpath": "uploaded_data/reports/upload.txt", "file_id": "file-upload"},
            {"source_relpath": "my_data/reports-other/not-a-match.txt", "file_id": "file-other"},
        ],
        subfolders=[],
    )

    assert list_scope_file_ids(
        temp_osii_root,
        {"scope_type": "folder", "folder_id": "folder-reports"},
    ) == ["file-current", "file-legacy", "file-upload"]
