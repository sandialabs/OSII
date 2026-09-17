def test_apply_reconciliation_marks_missing_source(temp_data_root, temp_osii_root):
    from osii.domain.extraction.common import init_doc_context
    from osii.domain.processing.reconcile import reconcile_osii_with_source
    from osii.domain.processing.reconcile_apply import apply_reconciliation
    from osii.domain.processing.source_status import get_source_status_value
    from osii.domain.storage.root_descriptor import write_root_toml
    from osii.domain.storage.folders import write_folder_manifest
    from osii.domain.storage.objects import write_meta_toml

    source_file = temp_data_root / "reports" / "example.pdf"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_bytes(b"%PDF-1.4 fake test content")

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
        docs=[{"source_relpath": "reports/example.pdf", "file_id": file_id}],
        subfolders=[],
        stats={
            "file_count": 1,
            "subfolder_count": 0,
            "total_bytes": len(b"%PDF-1.4 fake test content"),
            "latest_mtime_utc": "2026-05-21T00:00:00Z",
        },
        entrypoints=None,
    )

    write_meta_toml(
        temp_osii_root,
        file_id=file_id,
        source_relpath="reports/example.pdf",
        filename="example.pdf",
        mime="application/pdf",
        size_bytes=len(b"%PDF-1.4 fake test content"),
        mtime_utc=doc_ctx["mtime_utc"],
        sha256_hex=doc_ctx["sha256_hex"],
        extra_meta=None,
    )

    source_file.unlink()

    result = reconcile_osii_with_source(
        osii_root=temp_osii_root,
        data_root=temp_data_root,
    )
    assert result["summary"]["missing_source"] == 1

    applied = apply_reconciliation(
        reconcile_result=result,
        osii_root=temp_osii_root,
        data_root=temp_data_root,
        extractor_name=None,
        expert_context=None,
        rebuild_folders=False,
    )

    assert applied["missing_marked"] == 1
    assert get_source_status_value(temp_osii_root, file_id) == "missing_source"