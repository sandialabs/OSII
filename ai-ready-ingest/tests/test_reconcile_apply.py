from osii.extraction.common import init_doc_context
from osii.domain.storage.root_descriptor import write_root_toml
from osii.domain.storage.folders import write_folder_manifest
from osii.domain.storage.objects import append_manifest_record, write_meta_toml, write_text_file


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


def test_apply_reconciliation_updates_moved_relpath(temp_data_root, temp_osii_root):
    from osii.domain.processing.reconcile import reconcile_osii_with_source
    from osii.domain.processing.reconcile_apply import apply_reconciliation
    from osii.domain.read.docs import get_doc_meta

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

    applied = apply_reconciliation(
        reconcile_result=result,
        osii_root=temp_osii_root,
        data_root=temp_data_root,
        extractor_name=None,
        expert_context=None,
        rebuild_folders=False,
    )

    assert applied["moved_updated"] == 1

    meta = get_doc_meta(temp_osii_root, obj["file_id"])
    assert meta is not None
    assert meta["file"]["source_relpath"] == "renamed/example.pdf"


def test_apply_source_path_reconciliation_only_remaps_matching_hashes(
    temp_data_root,
    temp_osii_root,
):
    from osii.domain.processing.reconcile import reconcile_osii_with_source
    from osii.domain.processing.reconcile_apply import apply_source_path_reconciliation
    from osii.domain.read.docs import get_doc_meta

    content = b"%PDF-1.4 stable content identity"
    obj = _build_real_object_from_source(
        temp_data_root,
        temp_osii_root,
        "reports/example.pdf",
        content,
    )
    moved_path = temp_data_root / "archive" / "example.pdf"
    moved_path.parent.mkdir(parents=True, exist_ok=True)
    moved_path.write_bytes(content)
    obj["source_file"].unlink()

    result = reconcile_osii_with_source(
        osii_root=temp_osii_root,
        data_root=temp_data_root,
    )
    applied = apply_source_path_reconciliation(
        reconcile_result=result,
        osii_root=temp_osii_root,
        source_root=temp_data_root,
    )

    assert applied["moved_updated"] == 1
    assert applied["folder_tree_rebuilt"] is True
    meta = get_doc_meta(temp_osii_root, obj["file_id"])
    assert meta is not None
    assert meta["file"]["source_relpath"] == "archive/example.pdf"


def test_apply_reconciliation_rebuilds_folders(monkeypatch, temp_data_root, temp_osii_root):
    from osii.domain.processing.reconcile import reconcile_osii_with_source
    from osii.domain.processing.reconcile_apply import apply_reconciliation
    from osii.domain.read.catalog import load_folders_catalog

    content = b"%PDF-1.4 fake test content"
    _build_real_object_from_source(
        temp_data_root,
        temp_osii_root,
        "reports/example.pdf",
        content,
    )

    result = reconcile_osii_with_source(
        osii_root=temp_osii_root,
        data_root=temp_data_root,
    )

    def fake_dispatch_extract(**kwargs):
        return {"file_id": "fake", "osii_rel": "objects/fake", "error": None}

    monkeypatch.setattr("osii.domain.processing.reconcile_apply.dispatch_extract", fake_dispatch_extract)

    applied = apply_reconciliation(
        reconcile_result=result,
        osii_root=temp_osii_root,
        data_root=temp_data_root,
        extractor_name=None,
        expert_context=None,
        rebuild_folders=True,
    )

    assert applied["folder_tree_rebuilt"] is True

    folders = load_folders_catalog(temp_osii_root)
    assert len(folders) >= 1
