def test_get_object_source_route(client, temp_data_root, temp_osii_root):
    from osii.extraction.common import init_doc_context
    from osii.domain.storage.objects import write_meta_toml

    source_file = temp_data_root / "example_data" / "purcell.pdf"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_bytes(b"%PDF-1.4 fake pdf bytes")

    doc_ctx = init_doc_context(source_file, temp_data_root)
    file_id = doc_ctx["file_id"]

    write_meta_toml(
        temp_osii_root,
        file_id=file_id,
        source_relpath="example_data/purcell.pdf",
        filename="purcell.pdf",
        mime="application/pdf",
        size_bytes=source_file.stat().st_size,
        mtime_utc=doc_ctx["mtime_utc"],
        sha256_hex=doc_ctx["sha256_hex"],
        extra_meta=None,
    )

    response = client.get(f"/api/objects/{file_id}/source")
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF-1.4")


def test_get_object_source_route_with_data_volume_relative_path(
    client,
    test_app,
    temp_osii_root,
):
    from osii.extraction.common import init_doc_context
    from osii.domain.storage.objects import write_meta_toml

    shared_root = test_app.state.shared_volume_root.parent / "source"
    shared_root.mkdir(parents=True, exist_ok=True)
    test_app.state.shared_volume_root = shared_root

    source_file = shared_root / "reports" / "example.pdf"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_bytes(b"%PDF-1.4 data-volume-relative")

    doc_ctx = init_doc_context(source_file, shared_root.parent)
    file_id = doc_ctx["file_id"]
    write_meta_toml(
        temp_osii_root,
        file_id=file_id,
        source_relpath="source/reports/example.pdf",
        filename="example.pdf",
        mime="application/pdf",
        size_bytes=source_file.stat().st_size,
        mtime_utc=doc_ctx["mtime_utc"],
        sha256_hex=doc_ctx["sha256_hex"],
        extra_meta=None,
    )

    response = client.get(f"/api/objects/{file_id}/source")
    assert response.status_code == 200
    assert response.content == b"%PDF-1.4 data-volume-relative"
