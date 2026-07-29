from osii.extraction.common import init_doc_context
from osii.domain.storage.objects import write_meta_toml, write_text_file, append_manifest_record
from osii.domain.storage.folders import write_folder_manifest
from osii.domain.storage.root_descriptor import write_root_toml
from osii.domain.storage.ids import sha256_hex


def _build_real_object_from_source(temp_data_root, temp_osii_root, relpath: str, content: bytes):
    source_file = temp_data_root / relpath
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_bytes(content)

    doc_ctx = init_doc_context(source_file, temp_data_root)
    file_id = doc_ctx["file_id"]

    write_root_toml(
        temp_osii_root,
        root_folder_id="folder-root",
        host_path=str(temp_data_root),
        container_path=str(temp_data_root),
        notes="test root",
        tool_versions={"pipeline_version": "test"},
    )

    write_folder_manifest(
        temp_osii_root,
        folder_id="folder-root",
        path_hint="",
        docs=[{"source_relpath": relpath.replace("\\", "/"), "file_id": file_id}],
        subfolders=[],
        stats={
            "file_count": 1,
            "subfolder_count": 0,
            "total_bytes": len(content),
            "latest_mtime_utc": "2026-05-21T00:00:00Z",
        },
        entrypoints=None,
    )

    write_meta_toml(
        temp_osii_root,
        file_id=file_id,
        source_relpath=relpath.replace("\\", "/"),
        filename=source_file.name,
        mime="application/pdf",
        size_bytes=len(content),
        mtime_utc=doc_ctx["mtime_utc"],
        sha256_hex=doc_ctx["sha256_hex"],
        extra_meta=None,
    )

    text = "Thermal calibration drift was reduced."
    write_text_file(temp_osii_root, file_id, text)

    append_manifest_record(
        temp_osii_root,
        file_id,
        {
            "kind": "text",
            "id": "seg-000001",
            "path": "text.txt",
            "type": "page",
            "span": {
                "char_start": 0,
                "char_end": len(text),
            },
            "source_origin": {
                "source_type": "pdf",
                "unit_type": "page",
                "page": 1,
            },
            "related_ids": [],
        },
    )

    return {
        "file_id": file_id,
        "source_file": source_file,
        "relpath": relpath.replace("\\", "/"),
    }


def test_reconcile_unchanged(temp_data_root, temp_osii_root):
    from osii.domain.processing.reconcile import reconcile_osii_with_source

    obj = _build_real_object_from_source(
        temp_data_root,
        temp_osii_root,
        "reports/example.pdf",
        b"%PDF-1.4 fake test content",
    )

    result = reconcile_osii_with_source(
        osii_root=temp_osii_root,
        data_root=temp_data_root,
    )

    assert result["summary"]["unchanged"] == 1
    assert result["summary"]["changed"] == 0
    assert result["summary"]["moved"] == 0
    assert result["summary"]["missing_source"] == 0
    assert result["summary"]["new_files"] == 0


def test_reconcile_missing_source(temp_data_root, temp_osii_root):
    from osii.domain.processing.reconcile import reconcile_osii_with_source

    source_relpath = "reports/example.pdf"
    source_file = temp_data_root / source_relpath
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_bytes(b"%PDF-1.4 fake test content")

    obj = _build_real_object_from_source(
        temp_data_root,
        temp_osii_root,
        source_relpath,
        b"%PDF-1.4 fake test content",
    )

    source_file.unlink()

    result = reconcile_osii_with_source(
        osii_root=temp_osii_root,
        data_root=temp_data_root,
    )

    assert result["summary"]["missing_source"] == 1


def test_reconcile_new_file(temp_data_root, temp_osii_root):
    from osii.domain.processing.reconcile import reconcile_osii_with_source

    source_file = temp_data_root / "reports/newfile.pdf"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_bytes(b"%PDF-1.4 brand new file")

    result = reconcile_osii_with_source(
        osii_root=temp_osii_root,
        data_root=temp_data_root,
    )

    assert result["summary"]["new_files"] == 1


def test_reconcile_moved_file(temp_data_root, temp_osii_root):
    from osii.domain.processing.reconcile import reconcile_osii_with_source

    content = b"%PDF-1.4 fake test content"
    obj = _build_real_object_from_source(
        temp_data_root,
        temp_osii_root,
        "reports/example.pdf",
        content,
    )

    old_path = temp_data_root / "reports/example.pdf"
    new_path = temp_data_root / "renamed/example.pdf"
    new_path.parent.mkdir(parents=True, exist_ok=True)
    new_path.write_bytes(content)
    old_path.unlink()

    result = reconcile_osii_with_source(
        osii_root=temp_osii_root,
        data_root=temp_data_root,
    )

    assert result["summary"]["moved"] == 1