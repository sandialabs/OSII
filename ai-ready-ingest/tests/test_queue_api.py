from pathlib import Path


def test_browse_and_preview_report_processed_files(
    client,
    temp_data_root: Path,
    temp_osii_root: Path,
):
    from osii.domain.storage.folders import write_folder_manifest

    source_file = temp_data_root / "reports" / "finished.PDF"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_bytes(b"%PDF-1.4 processed")

    write_folder_manifest(
        temp_osii_root,
        folder_id="folder-root",
        path_hint="",
        docs=[
            {
                "source_relpath": "my_data/reports/finished.PDF",
                "file_id": "sha256-processed",
            }
        ],
        subfolders=[],
        stats={
            "file_count": 1,
            "subfolder_count": 0,
            "total_bytes": source_file.stat().st_size,
            "latest_mtime_utc": "",
        },
        entrypoints=None,
    )

    browse = client.get(
        "/api/browse",
        params={"path": str(source_file.parent), "include_patterns": "*.pdf"},
    )
    assert browse.status_code == 200
    assert browse.json()["entries"][0]["processed"] is True

    preview = client.post(
        "/api/resolve",
        json={
            "queue_paths": [str(temp_data_root)],
            "include_patterns": "*.pdf",
        },
    )
    assert preview.status_code == 200
    assert preview.json()["preview"]["matched_count"] == 1
    assert preview.json()["preview"]["processed_count"] == 1
    assert preview.json()["preview"]["unprocessed_count"] == 0


def test_upload_then_enqueue_returns_durable_run(client, temp_upload_root: Path):
    upload = client.post(
        "/api/uploads",
        files=[("files", ("notes.txt", b"hello from an upload", "text/plain"))],
    )

    assert upload.status_code == 200
    uploaded_path = upload.json()["uploads"][0]["path"]
    assert Path(uploaded_path).is_file()
    assert Path(uploaded_path).parent == temp_upload_root

    queued = client.post("/api/runs", json={"queue_paths": [uploaded_path]})

    assert queued.status_code == 200
    payload = queued.json()
    assert payload["id"] == payload["run_id"]
    assert payload["status"] == "queued"
    assert payload["resolved_count"] == 1

    status = client.get("/api/runs")
    assert status.status_code == 200
    assert status.json()["runs"][0]["id"] == payload["id"]
    assert status.json()["queue"][0]["status"] == "queued"
