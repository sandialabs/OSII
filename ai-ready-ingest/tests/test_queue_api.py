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
    assert preview.json()["preview"]["extractor_plan"] == [
        {
            "extension": ".pdf",
            "extractor": "tika",
            "count": 1,
            "sample": ["finished.PDF"],
        }
    ]

    overridden = client.post(
        "/api/resolve",
        json={
            "queue_paths": [str(temp_data_root)],
            "include_patterns": "*.pdf",
            "extractor_overrides": {".pdf": "osii_tesseract"},
        },
    )
    assert overridden.status_code == 200
    assert (
        overridden.json()["preview"]["extractor_plan"][0]["extractor"]
        == "osii_tesseract"
    )


def test_intake_readiness_reports_bundled_tools(
    client,
    monkeypatch,
):
    from osii.domain.processing import capability_readiness

    class Response:
        ok = True
        status_code = 200
        text = "ok"

    monkeypatch.setattr(
        capability_readiness.requests,
        "get",
        lambda *args, **kwargs: Response(),
    )
    monkeypatch.delenv("OSII_EMBEDDING_BASE_URL", raising=False)
    monkeypatch.delenv("OSII_MODEL_BASE_URL", raising=False)

    response = client.get("/api/intake/readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["extractors"][0]["id"] == "native_text"
    assert payload["extractors"][0]["available"] is True
    tika = next(item for item in payload["extractors"] if item["id"] == "tika")
    assert tika["available"] is True
    assert payload["synthesizers"] == []
    assert payload["embedders"][0]["available"] is False


def test_intake_readiness_hides_compatibility_duplicates_and_labels_model(
    client,
    monkeypatch,
):
    from osii.domain.processing import capability_readiness

    descriptors = [
        {
            "name": "local.native-text",
            "display_name": "Python text-layer PDF and Office extractor",
            "kind": "extractor",
            "base_url": "http://127.0.0.1:8092",
        },
        {
            "name": "local.extractive-preview",
            "display_name": "Cited source-excerpt preview (no AI)",
            "kind": "synthesizer",
            "base_url": "http://127.0.0.1:8093",
        },
        {
            "name": "ollama.synthesizer",
            "display_name": "Ollama Synthesizer",
            "kind": "synthesizer",
            "base_url": "http://127.0.0.1:8095/ollama/synthesizer",
        },
        {
            "name": "local.hashing",
            "display_name": "Lexical hashing vectors (no AI model)",
            "kind": "embedder",
            "base_url": "http://127.0.0.1:8085",
        },
        {
            "name": "local.stats-keywords",
            "display_name": "Document statistics and frequent keywords",
            "kind": "enricher",
            "base_url": "http://127.0.0.1:8094",
        },
    ]
    monkeypatch.setattr(
        capability_readiness,
        "discover_remote_processors",
        lambda **kwargs: descriptors,
    )
    monkeypatch.setattr(
        capability_readiness,
        "_service_probe",
        lambda *args, **kwargs: (False, "not running"),
    )
    monkeypatch.setattr(
        capability_readiness,
        "embedding_readiness",
        lambda osii_root: {
            "id": "ollama.embedder",
            "available": True,
            "model": "all-minilm",
        },
    )
    monkeypatch.setattr(
        capability_readiness,
        "_ollama_model_status",
        lambda model: (True, f"Ollama model {model} is installed."),
    )
    monkeypatch.setenv("OLLAMA_SYNTHESIS_MODEL", "llama3.2:3b")

    payload = client.get("/api/intake/readiness").json()

    assert [item["id"] for item in payload["extractors"]].count("native_text") == 0
    assert [item["id"] for item in payload["extractors"]].count(
        "local.native-text"
    ) == 1
    assert [item["id"] for item in payload["synthesizers"]].count("firstN") == 0
    ollama = next(
        item for item in payload["synthesizers"] if item["id"] == "ollama.synthesizer"
    )
    assert ollama["display_name"] == "Ollama Synthesizer · llama3.2:3b"
    assert ollama["model"] == "llama3.2:3b"
    assert ollama["available"] is True
    assert [item["id"] for item in payload["embedders"]] == [
        "ollama.embedder",
        "local.hashing",
    ]
    assert "local.stats-keywords" in [item["id"] for item in payload["enrichers"]]
    assert "stats_keywords" not in [item["id"] for item in payload["enrichers"]]


def test_ollama_adapter_is_not_ready_when_ollama_is_missing(
    client,
    monkeypatch,
):
    from osii.domain.processing import capability_readiness

    monkeypatch.setattr(
        capability_readiness,
        "discover_remote_processors",
        lambda **kwargs: [
            {
                "name": "ollama.synthesizer",
                "display_name": "Ollama Synthesizer",
                "kind": "synthesizer",
                "base_url": "http://127.0.0.1:8095/ollama/synthesizer",
            }
        ],
    )
    monkeypatch.setattr(
        capability_readiness,
        "_service_probe",
        lambda *args, **kwargs: (False, "not running"),
    )
    monkeypatch.setattr(
        capability_readiness,
        "embedding_readiness",
        lambda osii_root: {"id": "embedding", "available": False},
    )
    monkeypatch.setattr(
        capability_readiness,
        "_ollama_model_status",
        lambda model: (
            False,
            "OSII's adapter is running, but Ollama is not reachable.",
        ),
    )

    payload = client.get("/api/intake/readiness").json()
    ollama = payload["synthesizers"][0]

    assert ollama["available"] is False
    assert "Ollama is not reachable" in ollama["detail"]


def test_embedding_cannot_be_queued_without_a_tested_embedder(
    client,
    temp_data_root: Path,
    monkeypatch,
):
    source_file = temp_data_root / "notes.txt"
    source_file.write_text("local text", encoding="utf-8")
    monkeypatch.delenv("OSII_EMBEDDING_BASE_URL", raising=False)
    monkeypatch.delenv("OSII_MODEL_BASE_URL", raising=False)

    response = client.post(
        "/api/runs",
        json={
            "queue_paths": [str(source_file)],
            "build_embeddings": True,
        },
    )

    assert response.status_code == 409
    assert "no tested embedder is available" in response.json()["detail"]


def test_invalid_chunk_overlap_is_rejected_before_queueing(
    client,
    temp_data_root: Path,
):
    source_file = temp_data_root / "notes.txt"
    source_file.write_text("local text", encoding="utf-8")

    response = client.post(
        "/api/runs",
        json={
            "queue_paths": [str(source_file)],
            "build_embeddings": True,
            "chunking_method": "sentence_window",
            "chunk_size": 200,
            "chunk_overlap": 200,
        },
    )

    assert response.status_code == 422
    assert "smaller than chunk_size" in response.json()["detail"]


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


def test_intake_preserves_expert_context_on_the_run(
    client,
    temp_data_root: Path,
):
    source_file = temp_data_root / "calibration-notes.txt"
    source_file.write_text("ambient run 17", encoding="utf-8")

    queued = client.post(
        "/api/runs",
        json={
            "queue_paths": [str(source_file)],
            "expert_context": "  Temperatures are ambient unless marked.  ",
        },
    )

    assert queued.status_code == 200
    run = client.get(f"/api/runs/{queued.json()['run_id']}").json()
    assert run["expert_context"] == "Temperatures are ambient unless marked."


def test_intake_rejects_invalid_expert_context(
    client,
    temp_data_root: Path,
):
    source_file = temp_data_root / "notes.txt"
    source_file.write_text("test", encoding="utf-8")

    response = client.post(
        "/api/runs",
        json={
            "queue_paths": [str(source_file)],
            "expert_context": {"unexpected": "object"},
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "expert_context must be a string or null"
