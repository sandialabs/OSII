from pathlib import Path


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
