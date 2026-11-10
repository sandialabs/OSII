from pathlib import Path

import pytest


def test_starting_intake_does_not_read_all_original_bytes(client, temp_data_root, monkeypatch):
    source = temp_data_root / "document.txt"
    source.write_text("Worker reads these bytes after queueing.", encoding="utf-8")
    original_open = Path.open

    def defer_source_read(path, *args, **kwargs):
        if path == source:
            raise AssertionError("Intake start must not read source content before queueing")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", defer_source_read)
    response = client.post("/api/runs", json={"queue_paths": [str(source)]})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "queued"
    assert response.json()["resolved_count"] == 1


def test_slow_shared_drive_does_not_block_health(client, temp_data_root, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from osii.api import runs_routes

    source = temp_data_root / "document.txt"
    source.write_text("shared document", encoding="utf-8")
    entered, release = threading.Event(), threading.Event()
    expand = runs_routes.expand_queue_to_files

    def slow_scan(**kwargs):
        entered.set()
        assert release.wait(timeout=10)
        return expand(**kwargs)

    monkeypatch.setattr(runs_routes, "expand_queue_to_files", slow_scan)
    with client, ThreadPoolExecutor(max_workers=2) as pool:
        queued = pool.submit(client.post, "/api/runs", json={"queue_paths": [str(source)]})
        try:
            assert entered.wait(timeout=5)
            health = pool.submit(client.get, "/health")
            assert health.result(timeout=2).status_code == 200
        finally:
            release.set()
        assert queued.result(timeout=5).status_code == 200


def test_local_folder_selection_includes_files_and_preserves_uploads(
    client, tmp_path, temp_data_root, temp_upload_root,
):
    folder = tmp_path / "Research papers"
    nested = folder / "reports"
    nested.mkdir(parents=True)
    first = folder / "first.txt"
    second = nested / "second.txt"
    ignored = nested / "notes.tmp"
    uploaded = temp_upload_root / "upload.txt"
    for path in (first, second, ignored, uploaded):
        path.write_text(path.name, encoding="utf-8")

    browse = client.get("/api/browse", params={"path": str(folder)})
    assert browse.status_code == 200
    assert browse.json()["current_path"] == str(folder)
    assert browse.json()["folder_name"] == "Research papers"
    assert browse.json()["display_path"] == folder.as_posix()
    payload = {
        "queue_paths": [str(folder), str(uploaded)],
        "exclude_patterns": "reports/*.tmp",
    }
    preview = client.post("/api/resolve", json=payload)
    assert preview.status_code == 200
    assert {item["path"] for item in preview.json()["resolved_files"]} == {
        str(first), str(second), str(uploaded),
    }

    payload["excluded_paths"] = [str(second)]
    preview = client.post("/api/resolve", json=payload).json()
    assert preview["preview"]["matched_count"] == 2
    assert len(preview["preview"]["available_files"]) == 3  # Can re-check omitted files.
    queued = client.post("/api/runs", json=payload)
    assert queued.status_code == 200
    from osii.domain.processing.jobs import get_run
    run = get_run(queued.json()["id"])
    assert {item["path"] for item in run["items"]} == {str(first), str(uploaded)}


@pytest.mark.parametrize("host", ["/Users/researcher/Documents", r"C:\Users\researcher\Documents", r"\\server\share\Documents"])
def test_mounted_selection_translates_host_path_and_requires_launcher_for_other_folders(
    client, test_app, temp_data_root, tmp_path, monkeypatch, host,
):
    from pathlib import PureWindowsPath
    monkeypatch.setattr(test_app.state, "filesystem_mode", "mounted")
    monkeypatch.setattr(test_app.state, "shared_volume_host_path", host)
    child = temp_data_root / "reports"
    child.mkdir()
    host_path = PureWindowsPath(host) if PureWindowsPath(host).drive else Path(host)
    response = client.get("/api/browse", params={"path": str(host_path / "reports")})
    assert response.status_code == 200
    assert response.json()["current_path"] == str(child)
    assert response.json()["host_path"] == str(host_path / "reports")
    assert client.get("/api/browse").json()["parent_path"] is None
    different_host_folder = str(host_path.parent / "Other documents")
    assert client.get("/api/browse", params={"path": different_host_folder}).status_code == 403

    outside = tmp_path / "unconnected"
    outside.mkdir()
    denied = client.get("/api/browse", params={"path": str(outside)})
    assert denied.status_code == 403
    assert "Launcher" in denied.json()["detail"]
    assert client.post("/api/resolve", json={"queue_paths": [str(outside)]}).status_code == 403
    assert client.post("/api/runs", json={"queue_paths": [str(outside)]}).status_code == 403


def test_folder_errors_are_explicit_not_silent_fallbacks(client, temp_data_root, monkeypatch):
    missing = temp_data_root / "missing"
    assert client.get("/api/browse", params={"path": str(missing)}).status_code == 404
    assert client.post("/api/resolve", json={"queue_paths": [str(missing)]}).status_code == 404
    file = temp_data_root / "not-a-folder.txt"
    file.write_text("hello", encoding="utf-8")
    assert client.get("/api/browse", params={"path": str(file)}).status_code == 422
    original_iterdir = Path.iterdir

    def denied_iterdir(path):
        if path == temp_data_root:
            raise PermissionError("Access denied")
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", denied_iterdir)
    error = client.get("/api/browse")
    assert error.status_code == 403
    assert "cannot read" in error.json()["detail"]


def test_mounted_folder_does_not_follow_symlink_outside_connected_roots(
    client, test_app, temp_data_root, tmp_path, monkeypatch,
):
    monkeypatch.setattr(test_app.state, "filesystem_mode", "mounted")
    original = tmp_path / "outside.txt"
    original.write_text("outside", encoding="utf-8")
    try:
        (temp_data_root / "linked.txt").symlink_to(original)
    except OSError:
        pytest.skip("Creating symlinks requires permission on this platform")
    assert client.post("/api/resolve", json={"queue_paths": [str(temp_data_root)]}).status_code == 403


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
            "extractor": "local.native-text",
            "fallbacks": ["tika"],
            "count": 1,
            "sample": ["finished.PDF"],
        }
    ]

    overridden = client.post(
        "/api/resolve",
        json={
            "queue_paths": [str(temp_data_root)],
            "include_patterns": "*.pdf",
            "extractor_overrides": {".pdf": "toolchest.tesseract-opencv"},
        },
    )
    assert overridden.status_code == 200
    assert (
        overridden.json()["preview"]["extractor_plan"][0]["extractor"]
        == "toolchest.tesseract-opencv"
    )


def test_source_rescan_previews_then_applies_hash_matched_move(
    client,
    temp_data_root: Path,
    temp_osii_root: Path,
):
    from osii.extraction.common import init_doc_context
    from osii.domain.read.docs import get_doc_meta
    from osii.domain.storage.objects import (
        write_meta_toml,
        write_provenance_toml,
        write_text_file,
    )

    original = temp_data_root / "reports" / "example.pdf"
    original.parent.mkdir(parents=True, exist_ok=True)
    original.write_bytes(b"%PDF-1.4 exact bytes used as identity")
    context = init_doc_context(original, temp_data_root.parent)
    write_meta_toml(
        temp_osii_root,
        file_id=context["file_id"],
        source_relpath=context["source_relpath"],
        filename=original.name,
        mime=context["mime"],
        size_bytes=context["size_bytes"],
        mtime_utc=context["mtime_utc"],
        sha256_hex=context["sha256_hex"],
    )
    write_text_file(temp_osii_root, context["file_id"], "existing extraction")
    write_provenance_toml(
        temp_osii_root,
        context["file_id"],
        "test",
        status="done",
        extractor_name="test",
        extractor_version="1",
    )

    moved = temp_data_root / "archive" / original.name
    moved.parent.mkdir(parents=True, exist_ok=True)
    original.rename(moved)

    preview = client.post("/api/intake/rescan-sources", json={"apply": False})
    assert preview.status_code == 200
    assert preview.json()["summary"]["moved"] == 1
    assert "applied" not in preview.json()

    applied = client.post("/api/intake/rescan-sources", json={"apply": True})
    assert applied.status_code == 200
    assert applied.json()["applied"]["moved_updated"] == 1
    meta = get_doc_meta(temp_osii_root, context["file_id"])
    assert meta is not None
    assert meta["file"]["source_relpath"] == "my_data/archive/example.pdf"


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
    monkeypatch.delenv("NEMOTRON_BASE_URL", raising=False)

    response = client.get("/api/intake/readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["extractors"][0]["id"] == "native_text"
    assert payload["extractors"][0]["available"] is True
    tika = next(item for item in payload["extractors"] if item["id"] == "tika")
    assert tika["available"] is True
    assert tika["bundled"] is False
    assert tika["origin"]["label"] == "Optional Apache service"
    assert tika["origin"]["implementation"] == "compose.yaml: services.tika"
    assert payload["extractors"][0]["origin"]["label"] == "Bundled Core"
    assert payload["extractors"][0]["origin"]["configuration_file"].endswith("tools.toml")
    assert not any(item["id"] == "pdf_default" for item in payload["extractors"])
    assert payload["synthesizers"] == []
    assert payload["embedders"][0]["available"] is False


def test_nemotron_appears_only_when_explicitly_configured(client, monkeypatch):
    from osii.domain.processing import capability_readiness
    from osii.configuration import save_tools_config

    monkeypatch.setattr(capability_readiness, "_service_probe", lambda _: (True, "Connected"))
    monkeypatch.setattr(capability_readiness, "discover_remote_processors", lambda **_: [])
    monkeypatch.setattr(capability_readiness, "embedding_readiness", lambda _: {})
    monkeypatch.delenv("NEMOTRON_BASE_URL", raising=False)
    save_tools_config({"version": 1, "routes": {"extractor": [
        {"extractor": "banyan", "extensions": [".pdf"], "fallbacks": []},
    ]}})

    payload = client.get("/api/intake/readiness").json()
    legacy = next(item for item in payload["extractors"] if item["id"] == "pdf_default")
    assert legacy["available"] is False
    assert legacy["origin"]["label"] == "Configured legacy adapter"

    save_tools_config({"version": 1})
    monkeypatch.setenv("NEMOTRON_BASE_URL", "http://models.example.test/v1")
    payload = client.get("/api/intake/readiness").json()
    assert next(item for item in payload["extractors"] if item["id"] == "pdf_default")["available"] is True


def test_processor_origins_point_to_registration_or_model_configuration(client, monkeypatch):
    from osii.domain.processing import capability_readiness
    from osii.configuration import save_tools_config

    monkeypatch.setattr(capability_readiness, "_service_probe", lambda _: (True, "Connected"))
    monkeypatch.setattr(capability_readiness, "embedding_readiness", lambda _: {})
    monkeypatch.setattr(capability_readiness, "processor_model", lambda *_, **__: "chat-v1")
    save_tools_config({"version": 1, "tools": {"custom": {
        "processor_id": "example.custom", "kind": "enricher", "enabled": True,
        "runtime": {"endpoint": "http://custom.example.test"},
    }}})
    descriptors = [
        {"name": "example.custom", "kind": "enricher", "base_url": "http://custom.example.test"},
        {"name": "toolbox.readable-wiki", "kind": "enricher", "base_url": "http://127.0.0.1:8099"},
        {"name": "openai.synthesizer", "kind": "synthesizer", "base_url": "http://127.0.0.1:8095/openai/synthesizer"},
        {"name": "local.custom", "kind": "enricher", "base_url": "http://unknown.example.test"},
    ]
    monkeypatch.setattr(capability_readiness, "discover_remote_processors", lambda **_: descriptors)

    payload = client.get("/api/intake/readiness").json()
    enrichers = {item["id"]: item for item in payload["enrichers"]}
    assert enrichers["example.custom"]["origin"]["configuration_key"] == "tools.custom"
    assert enrichers["toolbox.readable-wiki"]["origin"]["label"] == "Optional Toolbox service"
    assert "builtin_tools_config" in enrichers["toolbox.readable-wiki"]["origin"]["implementation"]
    assert enrichers["local.custom"]["bundled"] is False
    assert payload["synthesizers"][0]["origin"]["configuration_file"].endswith("models.toml")


def test_intake_readiness_hides_compatibility_duplicates_and_labels_model(
    client,
    monkeypatch,
):
    from osii.configuration import load_models_config, save_models_config
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
    models = load_models_config()
    models["models"]["base"]["model"] = "llama3.2:3b"
    save_models_config(models)

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
    assert status.json()["worker"]["available"] is False


def test_intake_can_create_a_logical_collection_from_its_resolved_scope(
    client,
    temp_data_root: Path,
):
    source_file = temp_data_root / "project-aurora" / "brief.txt"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("intake collection", encoding="utf-8")

    queued = client.post(
        "/api/runs",
        json={
            "queue_paths": [str(source_file.parent)],
            "collection": {
                "name": "Project Aurora",
                "description": "Documents for the renewal review.",
            },
        },
    )

    assert queued.status_code == 200
    collection = queued.json()["collection"]
    assert collection["name"] == "Project Aurora"
    assert collection["description"] == "Documents for the renewal review."
    assert collection["kind"] == "intake"
    assert collection["document_count"] == 0

    run = client.get(f"/api/runs/{queued.json()['run_id']}").json()
    assert run["collection_id"] == collection["id"]


def test_run_control_api_pauses_resumes_and_cancels_a_queued_run(
    client,
    temp_data_root: Path,
):
    source_file = temp_data_root / "priority-control.txt"
    source_file.write_text("control this run", encoding="utf-8")
    queued = client.post("/api/runs", json={"queue_paths": [str(source_file)]})
    run_id = queued.json()["run_id"]

    paused = client.post(f"/api/runs/{run_id}/pause")
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "paused"

    resumed = client.post(f"/api/runs/{run_id}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "queued"

    cancelled = client.post(f"/api/runs/{run_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"


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


def test_selection_preview_never_reads_source_contents(client, temp_data_root, temp_osii_root, monkeypatch):
    from osii.domain.storage import ids
    for name in ('one.pdf', 'two.pdf'):
        (temp_data_root / name).write_bytes(b'not read during a metadata preview')
    original_open = Path.open
    def guarded_open(path, *args, **kwargs):
        if path.is_relative_to(temp_data_root):
            pytest.fail('Selection preview opened source contents')
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', guarded_open)
    monkeypatch.setattr(ids, 'compute_file_id', lambda *args: pytest.fail('Selection preview hashed content'))
    response = client.post('/api/resolve', json={
        'queue_paths': [str(temp_data_root)], 'synthesizer_name': 'openai.synthesizer',
        'build_embeddings': True, 'enricher_name': 'local.stats-keywords',
    })
    assert response.status_code == 200
    preview = response.json()['preview']
    assert preview['matched_count'] == 2
    assert preview['processing_plan']['estimated'] is True
    assert preview['processing_plan']['unique_document_count'] == 2  # Dedupe waits for processing.
    assert preview['processing_plan']['missing_extraction_count'] == 2
    assert not list((temp_osii_root / 'objects').glob('sha256-*'))


def test_slow_share_preview_does_not_block_api_health(test_app, temp_data_root, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from fastapi.testclient import TestClient
    from osii.api import intake_routes
    (temp_data_root / 'one.txt').write_text('metadata only')
    entered, release = threading.Event(), threading.Event()
    original = intake_routes.expand_queue_to_files
    def slow_share(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)
    monkeypatch.setattr(intake_routes, 'expand_queue_to_files', slow_share)
    with TestClient(test_app) as client, ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(client.post, '/api/resolve', json={'queue_paths': [str(temp_data_root)]})
        try:
            assert entered.wait(3)
            assert client.get('/health').status_code == 200
        finally:
            release.set()
        assert future.result(timeout=5).status_code == 200


def test_preview_directory_failure_is_actionable(client, temp_data_root, monkeypatch):
    from osii.api import intake_routes
    def denied(*args, **kwargs):
        raise PermissionError('private platform details')
    monkeypatch.setattr(intake_routes, 'expand_queue_to_files', denied)
    response = client.post('/api/resolve', json={'queue_paths': [str(temp_data_root)]})
    assert response.status_code == 503
    assert 'File inventory' in response.json()['detail']
    assert 'PermissionError' in response.json()['detail']
    assert 'private platform details' not in response.text


def test_paged_browse_is_nonrecursive_and_cancelable(client, temp_data_root):
    for i in range(225):
        (temp_data_root / f"paper-{i}.pdf").write_bytes(b"not read by browsing")
    nested = temp_data_root / "nested"
    nested.mkdir()
    (nested / "private-child.txt").write_text("not enumerated")
    first = client.get(
        "/api/browse/page", params={"path": str(temp_data_root), "limit": 40}
    )
    assert first.status_code == 200, first.text
    page = first.json()
    assert len(page["entries"]) <= 40
    assert page["cursor"]
    assert not any(item["name"] == "private-child.txt" for item in page["entries"])
    seen = {item["path"] for item in page["entries"]}
    cursor = page["cursor"]
    while cursor:
        response = client.get(
            "/api/browse/page", params={"cursor": cursor, "limit": 40}
        )
        assert response.status_code == 200, response.text
        page = response.json()
        paths = {item["path"] for item in page["entries"]}
        assert not seen & paths
        seen |= paths
        cursor = page["cursor"]
    assert len(seen) == 226
    assert (
        client.get("/api/browse/page", params={"cursor": "expired"}).status_code == 410
    )
    first = client.get(
        "/api/browse/page", params={"path": str(temp_data_root), "limit": 1}
    ).json()
    assert client.delete(f"/api/browse/page/{first['cursor']}").status_code == 200
    assert (
        client.get("/api/browse/page", params={"cursor": first["cursor"]}).status_code
        == 410
    )


def test_paged_browse_unavailable_paths_and_mounted_boundary(
    client, test_app, tmp_path, monkeypatch
):
    assert (
        client.get(
            "/api/browse/page", params={"path": str(tmp_path / "missing")}
        ).status_code
        == 404
    )
    monkeypatch.setattr(test_app.state, "filesystem_mode", "mounted")
    assert (
        client.get("/api/browse/page", params={"path": str(tmp_path)}).status_code
        == 403
    )


@pytest.mark.parametrize("reason", ["timeout", "disconnect"])
def test_browser_timeout_releases_process(reason):
    import asyncio
    import time
    from osii.domain.processing.directory_browse import DirectoryBrowsers

    class Process:
        terminated = False

        def is_alive(self):
            return True

        def terminate(self):
            self.terminated = True

        def join(self, timeout):
            pass

    class Connection:
        closed = False

        def send(self, value):
            pass

        def poll(self):
            return False

        def close(self):
            self.closed = True

    async def check():
        browsers = DirectoryBrowsers()
        process, connection = Process(), Connection()
        browsers.sessions["test"] = (
            process,
            connection,
            time.monotonic(),
            asyncio.Lock(),
        )

        async def connected():
            return reason == "disconnect"

        with pytest.raises(
            InterruptedError if reason == "disconnect" else TimeoutError
        ):
            await browsers.page("test", 10, connected, timeout=0.01)
        assert process.terminated and connection.closed
        assert not browsers.sessions

    asyncio.run(check())


def test_browse_roots_does_not_enumerate_directories(client, monkeypatch):
    import os

    def forbidden(*args, **kwargs):
        raise AssertionError("Navigation shortcuts must not enumerate directories")

    monkeypatch.setattr(os, "scandir", forbidden)
    response = client.get("/api/browse/roots")
    assert response.status_code == 200
    assert response.json()["items"]


def test_browser_page_limits_inspection_even_with_only_hidden_entries(
    tmp_path, monkeypatch
):
    from osii.domain.processing import directory_browse

    inspected = []

    class Directory:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def __next__(self):
            inspected.append(1)
            assert len(inspected) <= 5, (
                "Must not enumerate the directory to fill a filtered page"
            )
            return type("Entry", (), {"name": ".hidden"})()

    class Connection:
        responses = []
        polls = 0

        def poll(self, timeout):
            self.polls += 1
            return self.polls == 1

        def recv(self):
            return 5

        def send(self, value):
            self.responses.append(value)

        def close(self):
            pass

    monkeypatch.setattr(
        directory_browse, "resolve_intake_path", lambda *args, **kwargs: tmp_path
    )
    monkeypatch.setattr(directory_browse.os, "scandir", lambda *args: Directory())
    connection = Connection()
    directory_browse._reader(
        connection, None, str(tmp_path), str(tmp_path), "local", "", False
    )
    assert len(inspected) == 5
    assert connection.responses[0]["entries"] == []
    assert connection.responses[0]["has_more"]



@pytest.mark.parametrize("failed_status", ["error", "partial"])
def test_completed_run_retries_failed_files_without_reprocessing_successes(
    client, temp_data_root, temp_osii_root, monkeypatch, failed_status,
):
    from osii.api import runs_routes
    from osii.domain.processing.jobs import configure_job_store, claim_next_queue_job, complete_queue_job, get_run, save_run
    from osii.worker import execute_job
    configure_job_store(temp_osii_root)
    files = [temp_data_root / name for name in ("first.txt", "retry.txt", "last.txt")]
    for source in files:
        source.write_text(f"Source text for {source.name}.")
    original = runs_routes.dispatch_extract
    attempts = []
    fail = True
    def dispatch(**kwargs):
        source = kwargs["source_path"]
        attempts.append(source.name)
        if source.name == "retry.txt" and fail:
            raise RuntimeError("Temporary reader failure")
        kwargs["extractor_name"] = "native_text"
        return original(**kwargs)
    monkeypatch.setattr(runs_routes, "dispatch_extract", dispatch)
    queued = client.post("/api/runs", json={"queue_paths": [str(source) for source in files], "workflow": "intake"})
    assert queued.status_code == 200, queued.text
    run_id = queued.json()["id"]
    job = claim_next_queue_job("test-retry")
    execute_job(job)
    complete_queue_job(job["id"])
    run = get_run(run_id)
    assert run["status"] == "done"
    assert [item["status"] for item in run["items"]] == ["done", "error", "done"]
    completed_ids = [item.get("file_id") for item in run["items"] if item["status"] == "done"]
    run["items"][1]["status"] = failed_status
    save_run(run)
    initial_attempts = len(attempts)
    fail = False
    response = client.post(f"/api/runs/{run_id}/retry")
    assert response.status_code == 200, response.text
    job = claim_next_queue_job("test-retry-after-restart")
    execute_job(job)
    complete_queue_job(job["id"])
    retried = get_run(run_id)
    assert retried["status"] == "done"
    assert all(item["status"] == "done" for item in retried["items"])
    assert attempts[initial_attempts:] == ["retry.txt"]
    assert attempts.count("first.txt") == attempts.count("last.txt") == 1
    assert [retried["items"][i]["file_id"] for i in (0, 2)] == completed_ids
    # A fully successful run remains terminal.
    assert client.post(f"/api/runs/{run_id}/retry").status_code == 409


def test_browser_does_not_offer_symbolic_links_or_special_files(client, temp_data_root):
    import os
    if not hasattr(os, "mkfifo"):
        pytest.skip("POSIX special-file check")
    source = temp_data_root / "source.txt"
    source.write_text("An ordinary file")
    (temp_data_root / "linked.txt").symlink_to(source)
    os.mkfifo(temp_data_root / "pipe")
    response = client.get("/api/browse/page", params={"path": str(temp_data_root)})
    assert response.status_code == 200, response.text
    types = {entry["name"]: entry["type"] for entry in response.json()["entries"]}
    assert types == {"source.txt": "file", "linked.txt": "link", "pipe": "unavailable"}


@pytest.mark.parametrize("change", ["none", "source", "primary"])
def test_summary_retry_keeps_successful_extraction_even_when_reprocessing(
    client, temp_data_root, temp_osii_root, monkeypatch, change,
):
    from osii.api import runs_routes
    from osii.domain.processing.jobs import configure_job_store, claim_next_queue_job, complete_queue_job, get_run
    from osii.worker import execute_job
    configure_job_store(temp_osii_root)
    source = temp_data_root / "summary-retry.txt"
    source.write_text("Keep this completed extraction when retrying a summary.")
    original_extract = runs_routes.dispatch_extract
    calls = []
    fail = True
    def extract(**kwargs):
        calls.append("extract")
        kwargs["extractor_name"] = "native_text"
        return original_extract(**kwargs)
    class Synthesizer:
        def synthesize(self, **kwargs):
            calls.append("synthesize")
            if fail:
                raise RuntimeError("Temporary synthesis failure")
            from osii.synthesis.common import write_synth_text
            path = write_synth_text(osii_store=kwargs["osii_store"], file_id=kwargs["file_id"], text="# Recovered summary", synthesizer_name="test", synthesizer_version="1")
            return {"synthesis_rel": path.relative_to(kwargs["osii_store"]).as_posix(), "provenance_rel": f"objects/{kwargs['file_id']}/provenance.toml"}
    monkeypatch.setattr(runs_routes, "dispatch_extract", extract)
    monkeypatch.setattr(runs_routes, "get_synthesizer", lambda name: Synthesizer())
    response = client.post("/api/runs", json={"queue_paths": [str(source)], "extract_mode": "reprocess", "synthesizer_name": "local.extractive-preview"})
    assert response.status_code == 200, response.text
    run_id = response.json()["id"]
    job = claim_next_queue_job("initial")
    execute_job(job)
    complete_queue_job(job["id"])
    first = get_run(run_id)
    assert first["items"][0]["status"] == "partial"
    variant = first["items"][0]["extraction_variant_id"]
    if change == "source":
        source.write_text("Changed original bytes require a fresh extraction.")
    elif change == "primary":
        runs_routes.extract_document_variant(extractor_name="native_text", source_path=source,
            data_volume_root=temp_data_root.parent, osii_root=temp_osii_root, make_primary=True,
            dispatcher=original_extract)
    fail = False
    assert client.post(f"/api/runs/{run_id}/retry").status_code == 200
    job = claim_next_queue_job("retry")
    execute_job(job)
    complete_queue_job(job["id"])
    retried = get_run(run_id)
    assert retried["items"][0]["status"] == "done"
    if change == "source":
        assert retried["items"][0]["extraction_variant_id"] != variant
        assert calls == ["extract", "synthesize", "extract", "synthesize"]
    else:
        assert retried["items"][0]["extraction_variant_id"] == variant
        assert calls == ["extract", "synthesize", "synthesize"]
