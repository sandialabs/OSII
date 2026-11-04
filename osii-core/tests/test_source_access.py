from __future__ import annotations

from pathlib import Path

import pytest

from osii.domain.processing.source_access import source_access_summary, source_kind


def test_explicit_shared_source_uses_separate_writable_artifact_root(tmp_path: Path):
    source = tmp_path / "mounted-share"
    artifacts = tmp_path / "local-state" / ".osii"
    source.mkdir()
    artifacts.mkdir(parents=True)

    summary = source_access_summary(source, artifacts, configured_kind="shared")

    assert summary["kind"] == "shared"
    assert summary["available"] is True
    assert summary["ready_for_intake"] is True
    assert summary["osii_root"] == str(artifacts)
    assert "reads originals in place" in summary["detail"]


def test_unc_path_is_recognized_as_shared_without_contacting_server():
    assert source_kind(Path(r"\\server\department\documents")) == "shared"


def test_unavailable_share_has_actionable_status(tmp_path: Path):
    source = tmp_path / "disconnected-share"
    artifacts = tmp_path / ".osii"
    artifacts.mkdir()

    summary = source_access_summary(source, artifacts, configured_kind="shared")

    assert summary["available"] is False
    assert summary["source_mode"] == "unavailable"
    assert summary["ready_for_intake"] is False
    assert "not currently available" in summary["detail"]


def test_intake_readiness_reports_source_and_artifact_locations(client, test_app):
    test_app.state.source_kind = "shared"

    response = client.get("/api/intake/readiness")

    assert response.status_code == 200
    source = response.json()["source"]
    assert source["kind"] == "shared"
    assert source["source_root"] == str(test_app.state.shared_volume_root)
    assert source["osii_root"] == str(test_app.state.osii_root)
    assert source["ready_for_intake"] is True


@pytest.mark.parametrize("failure", ["offline", "denied", "interrupted"])
def test_failed_source_rescan_preserves_stored_documents(
    client, test_app, sample_osii_object, monkeypatch, failure,
):
    import os

    root = test_app.state.shared_volume_root
    stored = test_app.state.osii_root
    before = {
        path.relative_to(stored): path.read_bytes()
        for directory in ("objects", "folders")
        for path in (stored / directory).rglob("*")
        if path.is_file()
    }
    if failure == "offline":
        root.rmdir()
    else:
        blocked = root if failure == "denied" else root / "restricted"
        blocked.mkdir(exist_ok=True)
        scandir = os.scandir

        def failing_scandir(path):
            if Path(path) == blocked:
                error = PermissionError if failure == "denied" else OSError
                raise error("Shared drive access interrupted")
            return scandir(path)

        monkeypatch.setattr(os, "scandir", failing_scandir)

    response = client.post("/api/intake/rescan-sources", json={"apply": True})

    assert response.status_code == (403 if failure == "denied" else 503)
    assert "Reconnect" in response.json()["detail"]
    after = {
        path.relative_to(stored): path.read_bytes()
        for directory in ("objects", "folders")
        for path in (stored / directory).rglob("*")
        if path.is_file()
    }
    assert after == before


@pytest.mark.parametrize("location", ["local", "shared"])
def test_corpus_survives_process_restart(tmp_path, location):
    """Exercise real API/worker/processor processes; opt into a mounted share."""
    from contextlib import contextmanager, ExitStack
    import hashlib
    import os
    import socket
    import sqlite3
    import subprocess
    import sys
    import tempfile
    import time
    import unicodedata

    import httpx
    import pymupdf

    shared_directory = os.getenv("OSII_TEST_SHARED_DIR")
    if location == "shared" and not shared_directory:
        pytest.skip("Set OSII_TEST_SHARED_DIR to an existing writable mounted share")
    parent = Path(shared_directory) if location == "shared" else tmp_path
    checkout = Path(__file__).resolve().parents[2]
    artifacts = tmp_path / "runtime" / ".osii"

    def free_port():
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            return probe.getsockname()[1]

    api_port, extractor_port = free_port(), free_port()
    env = os.environ | {
        "PYTHONPATH": str(checkout / "osii-core"),
        "OSII_ROOT": str(artifacts),
        "UPLOAD_ORIGINALS_ROOT": str(tmp_path / "runtime" / "uploads"),
        "OSII_CONFIG_DIR": str(tmp_path / "config"),
        "OSII_ENV_FILE": str(tmp_path / "config" / "secrets.env"),
        "OSII_FILESYSTEM_MODE": "local",
        "OSII_SOURCE_KIND": "shared" if location == "shared" else "local",
        "OSII_PROCESSORS": f"http://127.0.0.1:{extractor_port}",
        "OSII_WORKER_POLL_SECONDS": "0.2",
    }

    @contextmanager
    def process(arguments, directory, name):
        with (tmp_path / f"{name}.log").open("a+") as log:
            child = subprocess.Popen(
                [sys.executable, "-m", *arguments], cwd=directory, env=env,
                stdout=log, stderr=subprocess.STDOUT,
            )
            try:
                yield child
            finally:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)

    with tempfile.TemporaryDirectory(prefix="osii-shared-check-", dir=parent) as directory:
        source = Path(directory)
        original = source / "Résumé calibration check.pdf"
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((72, 72), "OSII NAS verification: zirconium calibration evidence.")
            pdf.new_page().insert_text((72, 72), "Second page preserves source provenance.")
            pdf.save(original)
        digest = hashlib.sha256(original.read_bytes()).hexdigest()
        file_id = "sha256-" + digest
        env.update({"SHARED_VOLUME_ROOT": str(source), "SHARED_VOLUME_HOST_PATH": str(source)})

        with httpx.Client(base_url=f"http://127.0.0.1:{api_port}", trust_env=False, timeout=20) as client:
            for restart in (False, True):
                with ExitStack() as stack:
                    extractor = stack.enter_context(process(
                        ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(extractor_port)],
                        checkout / "osii-core/services/local-extractor", "extractor",
                    ))
                    api = stack.enter_context(process(
                        ["uvicorn", "osii.main:app", "--host", "127.0.0.1", "--port", str(api_port)],
                        checkout / "osii-core", "api",
                    ))
                    worker = stack.enter_context(process(["osii.worker"], checkout / "osii-core", "worker"))
                    deadline = time.monotonic() + 30
                    while True:
                        assert all(child.poll() is None for child in (api, worker, extractor)), "See process logs in test temp directory"
                        try:
                            ready = client.get("/health").is_success and client.get(
                                f"http://127.0.0.1:{extractor_port}/health"
                            ).is_success
                            if ready:
                                break
                        except httpx.TransportError:
                            pass
                        assert time.monotonic() < deadline, "Processes did not become healthy"
                        time.sleep(0.1)

                    if not restart:
                        response = client.post("/api/runs", json={
                            "queue_paths": [str(source)],
                            "extractor_overrides": {".pdf": "local.native-text"},
                        })
                        assert response.status_code == 200, response.text
                        run_id = response.json()["id"]
                        deadline = time.monotonic() + 60
                        while True:
                            run = client.get(f"/api/runs/{run_id}").json()
                            if run["status"] in {"done", "error"}:
                                break
                            assert time.monotonic() < deadline, run
                            time.sleep(0.1)
                        assert run["status"] == "done", run
                        assert run["items"][0]["status"] == "done", run
                        assert run["items"][0]["osii"] == f"objects/{file_id}"

                    response = client.post("/api/search", json={"query": "zirconium", "mode": "lexical"})
                    assert response.status_code == 200, response.text
                    assert response.json()["results"][0]["file_id"] == file_id
                    assert "zirconium" in client.get(f"/api/objects/{file_id}/texts/preferred").json()["text"]
                    assert client.get(f"/api/objects/{file_id}/source").content == original.read_bytes()
                    assert client.get(f"/api/runs/{run_id}").json()["status"] == "done"

                    if restart:
                        # Hide only our test corpus; never unmount the user's share.
                        offline = source.with_name(source.name + "-offline")
                        source.rename(offline)
                        try:
                            assert client.get("/api/browse").status_code == 404
                            failed = client.post("/api/intake/rescan-sources", json={"apply": True})
                            assert failed.status_code == 503, failed.text
                            assert not (artifacts / "objects" / file_id / "source_status.toml").exists()
                            assert client.post("/api/search", json={
                                "query": "zirconium", "mode": "lexical",
                            }).json()["results"][0]["file_id"] == file_id
                        finally:
                            offline.rename(source)
                        assert client.get(f"/api/objects/{file_id}/source").content == original.read_bytes()

        assert hashlib.sha256(original.read_bytes()).hexdigest() == digest
        assert {unicodedata.normalize("NFC", path.name) for path in source.iterdir()} == {original.name}
        for database in (artifacts / "state").glob("*.sqlite3"):
            with sqlite3.connect(database) as connection:
                assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
