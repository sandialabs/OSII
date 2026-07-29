def test_apply_reconciliation_uses_routing_for_new_files(monkeypatch, temp_data_root, temp_osii_root):
    from osii.domain.processing.reconcile import reconcile_osii_with_source
    from osii.domain.processing.reconcile_apply import apply_reconciliation

    source_file = temp_data_root / "reports" / "newfile.pdf"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_bytes(b"%PDF-1.4 brand new file")

    result = reconcile_osii_with_source(
        osii_root=temp_osii_root,
        data_root=temp_data_root,
    )
    assert result["summary"]["new_files"] == 1

    calls = []

    def fake_dispatch_extract(
        *,
        extractor_name,
        source_path,
        data_volume_root,
        osii_store,
        expert_context=None,
        extractor_config=None,
    ):
        calls.append(
            {
                "extractor_name": extractor_name,
                "source_path": str(source_path),
            }
        )
        return {"file_id": "fake", "osii_rel": "objects/fake", "error": None}

    monkeypatch.setattr("osii.domain.processing.reconcile_apply.dispatch_extract", fake_dispatch_extract)

    applied = apply_reconciliation(
        reconcile_result=result,
        osii_root=temp_osii_root,
        data_root=temp_data_root,
        extractor_name=None,
        expert_context=None,
        rebuild_folders=False,
    )

    assert applied["extracted_new"] == 1
    assert len(calls) == 1
    assert calls[0]["extractor_name"] in {"pdf_default", "tika", "textract"}