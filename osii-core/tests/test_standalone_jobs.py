"""Durable compatibility APIs, including actual process death and restart."""

import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from osii.domain.processing import jobs
from osii.worker import execute_job
from osii.configuration import save_models_config
from osii.domain.catalog_db import rebuild_catalog
from osii.domain.scopes.collections import (
    create_collection,
    add_documents_to_collection,
)
from test_incremental_embeddings import document


def child(root, code):
    environment = dict(
        os.environ,
        OSII_ROOT=str(root),
        SHARED_VOLUME_ROOT=str(root.parent / "source"),
        UPLOAD_ORIGINALS_ROOT=str(root.parent / "uploads"),
    )
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    return subprocess.run(
        [sys.executable, "-c", code],
        env=environment,
        cwd=root.parent,
        capture_output=True,
        text=True,
        timeout=25,
    )


@pytest.mark.parametrize("scope_type", ["object", "collection"])
def test_synthesis_recovers_after_process_exit_and_preserves_inputs(
    client, temp_osii_root, sample_osii_object, monkeypatch, scope_type
):
    monkeypatch.delenv("OSII_SYNTHESIZER_FALLBACKS", raising=False)
    root, file_id = temp_osii_root, sample_osii_object["file_id"]
    if scope_type == "object":
        endpoint = f"/api/synthesis/objects/{file_id}"
        name = "firstN"
    else:
        collection = create_collection(
            root, name="Restart collection", description=None, kind="manual", color=None
        )
        add_documents_to_collection(root, collection["id"], [file_id])
        endpoint = f"/api/collections/{collection['id']}/syntheses"
        name = "collection_firstn"
    response = client.post(endpoint, json={"synthesizer_name": name})
    assert response.status_code == 200, response.text
    run_id = response.json()["run_id"]
    assert jobs.find_active_jobs_for_paths([str(root / "objects" / file_id)])
    # The API returned before processing; kill a worker after it claimed the job.
    crashed = child(
        root,
        "from osii.domain.processing.jobs import *; import os; from pathlib import Path; configure_job_store(Path(os.environ['OSII_ROOT'])); assert claim_next_queue_job(); os._exit(9)",
    )
    assert crashed.returncode == 9, crashed.stderr
    assert jobs.recover_stale_queue_jobs(stale_after_seconds=0) == [run_id]
    (root / "objects" / file_id / "text.txt").write_text("Changed after submission")
    (root / "objects" / file_id / "synth.txt").write_text("Changed after submission")
    # Now die after results are persisted, before acknowledging the queue job.
    saved = child(
        root,
        "from osii.domain.processing.jobs import *; from osii.worker import execute_job; import os; from pathlib import Path; configure_job_store(Path(os.environ['OSII_ROOT'])); execute_job(claim_next_queue_job()); os._exit(9)",
    )
    assert saved.returncode == 9, saved.stderr
    result = jobs.get_run(run_id)["items"][0]["synthesis"]
    output = root / (result["text_path"] if isinstance(result, dict) else result)
    text, changed = output.read_text(), output.stat().st_mtime_ns
    assert "Changed after submission" not in text
    assert "calibration" in text
    jobs.recover_stale_queue_jobs(stale_after_seconds=0)
    resumed = child(
        root,
        "from osii.domain.processing.jobs import *; from osii.worker import execute_job; import os; from pathlib import Path; configure_job_store(Path(os.environ['OSII_ROOT'])); job=claim_next_queue_job(); execute_job(job); complete_queue_job(job['id'])",
    )
    assert resumed.returncode == 0, resumed.stderr
    assert output.stat().st_mtime_ns == changed
    assert jobs.get_run(run_id)["status"] == "done"


def test_synthesis_failure_is_retryable_on_same_inputs(
    client, temp_osii_root, sample_osii_object, monkeypatch
):
    monkeypatch.delenv("OSII_SYNTHESIZER_FALLBACKS", raising=False)
    file_id = sample_osii_object["file_id"]
    response = client.post(
        f"/api/synthesis/objects/{file_id}", json={"synthesizer_name": "firstN"}
    )
    run_id = response.json()["run_id"]
    from osii.synthesis.file.firstn import FirstNSynthesizer

    with monkeypatch.context() as patch:
        patch.setattr(
            FirstNSynthesizer,
            "synthesize",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("temporary failure")),
        )
        job = jobs.claim_next_queue_job()
        with pytest.raises(RuntimeError, match="temporary failure"):
            execute_job(job)
        jobs.complete_queue_job(job["id"], error="temporary failure")
    assert client.post(f"/api/runs/{run_id}/retry").status_code == 200
    execute_job(jobs.claim_next_queue_job())
    assert jobs.get_run(run_id)["status"] == "done"


def test_full_index_alias_is_durable_and_each_run_has_immutable_status(
    client, temp_osii_root, sample_osii_object
):
    first = client.post("/api/embeddings/build", json={}).json()
    second = client.post("/api/embeddings/build", json={}).json()
    assert first["job_id"] == second["job_id"] == "segments"
    assert first["status"] == "running" and first["queue_status"] == "queued"
    assert first["run_id"] != second["run_id"]
    assert (
        client.get("/api/embeddings/build/segments").json()["run_id"]
        == second["run_id"]
    )
    assert (
        client.get(f"/api/embeddings/build/{first['run_id']}").json()["run_id"]
        == first["run_id"]
    )
    check = child(
        temp_osii_root,
        f"from osii.main import app; from fastapi.testclient import TestClient; data=TestClient(app).get('/api/embeddings/build/segments').json(); assert data['run_id']=={second['run_id']!r}, data",
    )
    assert check.returncode == 0, check.stderr
    assert "error" in client.get("/api/embeddings/build/unknown").json()


def test_full_index_resumes_vectors_after_worker_is_killed(
    client, temp_osii_root, monkeypatch
):
    root = temp_osii_root
    document(root, "one", "First document text")
    document(root, "two", "Second document text")
    rebuild_catalog(root)
    waiting, release = threading.Event(), threading.Event()
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            text = request["input"][0]
            calls.append(text)
            if len(calls) == 2:
                waiting.set()
                release.wait(15)
            payload = json.dumps(
                {"data": [{"index": 0, "embedding": [1.0, 2.0, 3.0]}]}
            ).encode()
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/v1"
    monkeypatch.setenv("OSII_ROOT", str(root))
    monkeypatch.setenv("OSII_EMBEDDING_BASE_URL", url)
    monkeypatch.setenv("OSII_EMBEDDING_API_KEY", "test-key")
    save_models_config(
        {
            "version": 1,
            "defaults": {"embedding": "test"},
            "models": {
                "test": {
                    "type": "openai-compatible",
                    "model": "test-model",
                    "base_url": url,
                    "capabilities": ["embedding"],
                    "enabled": True,
                }
            },
        }
    )
    response = client.post(
        "/api/embeddings/build", json={"batch_size": 1, "chunking_method": "paragraph"}
    )
    assert response.status_code == 200, response.text
    run_id = response.json()["run_id"]
    environment = dict(
        os.environ,
        OSII_ROOT=str(root),
        PYTHONPATH=str(Path(__file__).resolve().parents[1]),
    )
    command = "from pathlib import Path; import os; from osii.domain.processing.jobs import *; from osii.worker import execute_job; configure_job_store(Path(os.environ['OSII_ROOT'])); job=claim_next_queue_job(); execute_job(job); complete_queue_job(job['id'])"
    process = subprocess.Popen(
        [sys.executable, "-c", command],
        env=environment,
        cwd=root.parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert waiting.wait(12), "Worker did not start its second request"
        process.kill()
        process.communicate(timeout=10)
        assert jobs.recover_stale_queue_jobs(stale_after_seconds=0) == [run_id]
        release.set()
        resumed = child(root, command)
        assert resumed.returncode == 0, resumed.stderr
        assert Counter(calls)[calls[0]] == 1  # The committed first chunk was reused.
        assert jobs.get_run(run_id)["status"] == "done"
        assert client.get("/api/embeddings/build/segments").json()["status"] == "done"
    finally:
        release.set()
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_full_index_api_reports_failure_and_retries_only_missing_vectors(
    client, temp_osii_root, monkeypatch
):
    from test_incremental_embeddings import Client
    from osii.indexing import incremental

    root, provider = temp_osii_root, Client()
    monkeypatch.setenv("OSII_ROOT", str(root))
    save_models_config(
        {
            "version": 1,
            "defaults": {"embedding": "test"},
            "models": {
                "test": {
                    "type": "openai-compatible",
                    "model": "test-model",
                    "base_url": provider.base_url,
                    "capabilities": ["embedding"],
                    "enabled": True,
                }
            },
        }
    )
    monkeypatch.setattr(incremental, "create_embedding_client", lambda: provider)
    monkeypatch.setattr("osii.indexing.common.time.sleep", lambda _: None)
    document(root, "good", "Healthy document")
    bad = document(root, "bad", "Rejected document")
    rebuild_catalog(root)
    provider.bad.add("Rejected document")
    submitted = client.post(
        "/api/embeddings/build", json={"batch_size": 1, "chunking_method": "paragraph"}
    ).json()
    run_id = submitted["run_id"]
    job = jobs.claim_next_queue_job()
    with pytest.raises(incremental.IncrementalEmbeddingError) as failure:
        execute_job(job)
    jobs.complete_queue_job(job["id"], error=str(failure.value))
    status = client.get("/api/embeddings/build/segments").json()
    assert status["status"] == "error"
    assert bad in status["progress"]["failures"]
    assert status["progress"]["completed_documents"] == 1
    provider.bad.clear()
    provider.calls.clear()
    assert client.post(f"/api/runs/{run_id}/retry").status_code == 200
    job = jobs.claim_next_queue_job()
    execute_job(job)
    jobs.complete_queue_job(job["id"])
    assert provider.calls == [["Rejected document"]]
    assert client.get(f"/api/embeddings/build/{run_id}").json()["status"] == "done"
    assert jobs.get_run(run_id)["completed"] == 2


def test_native_synthesis_does_not_depend_on_unrelated_model_changes(
    client, temp_osii_root, sample_osii_object, monkeypatch
):
    monkeypatch.delenv("OSII_SYNTHESIZER_FALLBACKS", raising=False)
    response = client.post(
        f"/api/synthesis/objects/{sample_osii_object['file_id']}",
        json={"synthesizer_name": "firstN"},
    )
    save_models_config({"version": 1, "defaults": {}, "models": {}})
    execute_job(jobs.claim_next_queue_job())
    assert jobs.get_run(response.json()["run_id"])["status"] == "done"
