"""Discovery failure boundaries and the normal sidecar Intake handoff."""

from pathlib import Path
import json
import sqlite3
import threading
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from osii.volume.models import Filters, ScanOptions, SelectionRequest
from osii.volume.store import SCHEMA, VolumeStore, _statements
from osii.volume.worker import execute


def work(store):
    job = store.claim("discovery-test")
    assert job
    execute(store, job, "discovery-test", threading.Event())
    return store.run(job["id"])


@pytest.fixture
def inventory(tmp_path):
    root = tmp_path / "share"
    root.mkdir()
    store = VolumeStore(tmp_path / "inventory.sqlite3")
    store.initialize()
    source = store.register_source(root)
    return store, root, source["id"]


def test_migration_preserves_evidence_and_requires_backup(tmp_path):
    path = tmp_path / "v1.sqlite3"
    with sqlite3.connect(path) as conn:
        _statements(conn, SCHEMA)
        conn.execute("PRAGMA user_version=1")
        conn.execute("INSERT INTO sources VALUES(1,'old','/old','1','2')")
        conn.execute("INSERT INTO selections VALUES(1,'{}',1,0,0)")
    store = VolumeStore(path)
    with pytest.raises(ValueError, match="explicit migration"):
        store.initialize()
    backup = tmp_path / "backup.sqlite3"
    store.migrate(backup)
    store.initialize()
    assert store.source(1)["root"] == "/old"
    assert store.selection(1)["created"] == 1
    with sqlite3.connect(backup) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    assert backup.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError):
        store.migrate(backup)


def test_stat_failure_keeps_readable_siblings_unknown_size_and_no_false_absence(
    inventory, monkeypatch
):
    store, root, sid = inventory
    for name in ("readable.txt", "denied.txt", "old.txt"):
        (root / name).write_text(name)
    store.new_scan(sid, ScanOptions(readers=1, isolate=False, show_hidden=True))
    assert work(store)["status"] == "done"
    (root / "old.txt").unlink()
    import osii.domain.processing.directory_scan as scanner

    original = scanner.os.scandir

    class Children:
        def __init__(self, path):
            self.inner = original(path)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.inner.close()

        def __iter__(self):
            for child in self.inner:
                if child.name == "denied.txt":

                    def denied(**kwargs):
                        raise PermissionError("test")

                    yield SimpleNamespace(name=child.name, stat=denied)
                else:
                    yield child

    monkeypatch.setattr(scanner.os, "scandir", Children)
    rid = store.new_scan(sid, ScanOptions(readers=1, isolate=False, show_hidden=True))
    assert work(store)["status"] == "error"
    names = {e["name"]: e for e in store.entries(Filters())["items"]}
    assert names["denied.txt"]["size_bytes"] is None
    assert names["readable.txt"]["scan_run_id"] == rid
    assert (
        names["old.txt"]["status"] == "present"
    )  # Failed directory cannot establish deletion.
    with pytest.raises(ValueError, match="incomplete"):
        store.select(SelectionRequest())
    partial = store.select(SelectionRequest(allow_partial=True))
    assert (
        partial["count"] == 1
    )  # Neither unknown metadata nor old unvisited observation.
    monkeypatch.setattr(scanner.os, "scandir", original)
    store.control(rid, "resume")
    assert work(store)["status"] == "done"
    assert store.summary(Filters())["files"] == 2


def test_rules_and_real_isolated_readers_do_not_open_documents(inventory, monkeypatch):
    store, root, sid = inventory
    (root / "keep.txt").write_text("content")
    (root / "ignore.pdf").write_text("content")
    (root / ".hidden.txt").write_text("content")
    (root / "nested").mkdir()
    (root / "nested" / "deep.txt").write_text("content")
    # The scanner process only stats originals; source writes/opens are not part
    # of its protocol. Exercise the production spawn path with two readers.
    store.new_scan(sid, ScanOptions(include_patterns=["*.txt"], readers=2))
    result = work(store)
    assert result["status"] == "done", result
    assert {e["path"] for e in store.entries(Filters())["items"]} == {
        "keep.txt",
        "nested/deep.txt",
    }
    store.new_scan(sid, ScanOptions(include_patterns=["*.txt"], max_depth=0))
    assert work(store)["status"] == "done"
    selected = store.select(SelectionRequest())
    assert [m["path"] for m in store.staged_members(selected["id"])] == ["keep.txt"]


def stalled_reader(source, relative, options, output):
    time.sleep(20)


def test_stalled_reader_timeout_opens_circuit_and_resume_recovers(
    inventory, monkeypatch
):
    store, root, sid = inventory
    (root / "read.txt").write_text("text")
    from osii.volume import scanner

    original = scanner._reader
    monkeypatch.setattr(scanner, "_reader", stalled_reader)
    rid = store.new_scan(sid, ScanOptions(readers=1, timeout_seconds=1))
    started = time.monotonic()
    result = work(store)
    assert time.monotonic() - started < 6
    assert result["status"] == "error"
    assert "circuit breaker" in result["error"]
    monkeypatch.setattr(scanner, "_reader", original)
    store.control(rid, "resume")
    assert work(store)["status"] == "done"


def test_byte_budget_frozen_metadata_and_paged_members(inventory):
    store, root, sid = inventory
    for n in range(5):
        (root / f"{n}.txt").write_text("abcd")
    store.new_scan(sid, ScanOptions(readers=1, isolate=False, show_hidden=True))
    work(store)
    selection = store.select(SelectionRequest(max_files=4, max_bytes=9))
    assert selection["count"] == 2 and selection["bytes"] == 8
    members = store.staged_members(selection["id"])
    page = store.selection_entries(selection["id"], limit=1)
    assert page["next_cursor"] is not None
    assert (
        len(
            store.selection_entries(
                selection["id"], after=page["next_cursor"], limit=1
            )["items"]
        )
        == 1
    )
    (root / members[0]["path"]).write_text("changed and larger")
    from osii.volume.staging import validate_member

    with pytest.raises(ValueError, match="changed"):
        validate_member({"database": str(store.path)}, members[0])
    store.new_scan(sid, ScanOptions(readers=1, isolate=False, show_hidden=True))
    work(store)
    assert store.selection(selection["id"])["bytes"] == 8
    assert store.selection_entries(selection["id"])["items"][0]["size_bytes"] == 4
    with pytest.raises(ValueError, match="stale"):
        store.staged_members(selection["id"])


def stage_for_client(temp_osii_root, temp_data_root, monkeypatch):
    monkeypatch.delenv("OSII_INVENTORY_DB", raising=False)
    monkeypatch.delenv("OSII_VOLUME_DB", raising=False)
    store = VolumeStore(temp_osii_root / "state" / "inventory.sqlite3")
    store.initialize()
    sid = store.register_source(temp_data_root)["id"]
    store.new_scan(sid, ScanOptions(readers=1, isolate=False, show_hidden=True))
    work(store)
    return store, store.select(SelectionRequest())


def test_review_and_handoff_never_walk_stat_or_hash_sources(
    client, temp_osii_root, temp_data_root, monkeypatch
):
    (temp_data_root / "test.txt").write_text("source")
    store, selection = stage_for_client(temp_osii_root, temp_data_root, monkeypatch)
    from osii.api import runs_routes
    from osii.domain.processing.jobs import configure_job_store, list_queue_jobs

    configure_job_store(temp_osii_root)

    def blocked(*args, **kwargs):
        raise AssertionError("Source I/O during handoff")

    monkeypatch.setattr(runs_routes, "expand_queue_to_files", blocked)
    monkeypatch.setattr(runs_routes, "compute_file_id", blocked)
    original_stat = Path.stat

    def stat(path, *args, **kwargs):
        if path == temp_data_root or path.is_relative_to(temp_data_root):
            return blocked()
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stat)
    payload = {"inventory_selection_id": selection["id"]}
    preview = client.post("/api/resolve", json=payload)
    assert preview.status_code == 200, preview.text
    first = client.post("/api/runs", json=payload)
    assert first.status_code == 200, first.text
    second = client.post("/api/runs", json=payload)
    assert second.status_code == 200, second.text
    assert first.json()["id"] == second.json()["id"]
    assert len(list_queue_jobs()) == 1


def test_staged_intake_bad_file_continues_and_writes_normal_sidecars(
    client, temp_osii_root, temp_data_root, monkeypatch
):
    for name in ("bad.txt", "good.txt", "last.txt"):
        (temp_data_root / name).write_text(f"Grounded source text {name}.")
    (temp_data_root / "broken.pdf").write_bytes(b"%PDF-corrupt")
    store, selection = stage_for_client(temp_osii_root, temp_data_root, monkeypatch)
    from osii.domain.processing.jobs import (
        configure_job_store,
        claim_next_queue_job,
        get_run,
    )
    from osii.api import runs_routes
    from osii.worker import execute_job
    from osii.domain.scopes.membership import list_scope_file_ids

    configure_job_store(temp_osii_root)
    queued = client.post(
        "/api/runs",
        json={
            "inventory_selection_id": selection["id"],
            "extractor_overrides": {".pdf": "native_text"},
        },
    )
    assert queued.status_code == 200, queued.text
    (temp_data_root / "bad.txt").write_text("changed after staging")
    original_dispatch = runs_routes.dispatch_extract
    called = []

    def dispatch(**kwargs):
        called.append(str(kwargs["source_path"]))
        if Path(kwargs["source_path"]).suffix == ".pdf":
            raise ValueError("Corrupt PDF")
        kwargs["extractor_name"] = "native_text"
        return original_dispatch(**kwargs)

    monkeypatch.setattr(runs_routes, "dispatch_extract", dispatch)
    job = claim_next_queue_job("test")
    execute_job(job)
    run = get_run(queued.json()["id"])
    assert run["status"] == "done", run
    statuses = {Path(i["path"]).name: i["status"] for i in run["items"]}
    assert statuses == {
        "bad.txt": "error",
        "broken.pdf": "error",
        "good.txt": "done",
        "last.txt": "done",
    }, run
    assert all(item.get("file_id") for item in run["items"] if item["status"] == "done")
    assert run["completed"] == 4
    assert len(called) == 3
    assert len(list_scope_file_ids(temp_osii_root, {"scope_type": "root"})) == 2
    assert store.summary(Filters(sidecar_state="processed"))["files"] == 2
    manifest = json.loads(Path(run["manifest_path"]).read_text())
    assert manifest["inventory_selection_id"] == selection["id"]
    assert all(item["sha256"] is None for item in manifest["files"])


def test_handoff_recovers_api_exit_between_run_and_queue_writes(
    client, temp_osii_root, temp_data_root, monkeypatch
):
    (temp_data_root / "test.txt").write_text("source")
    _, selection = stage_for_client(temp_osii_root, temp_data_root, monkeypatch)
    from osii.api import runs_routes
    from osii.domain.processing.jobs import configure_job_store, list_queue_jobs

    configure_job_store(temp_osii_root)
    original = runs_routes.enqueue_run

    def crash(*args, **kwargs):
        raise RuntimeError("simulated API exit")

    monkeypatch.setattr(runs_routes, "enqueue_run", crash)
    payload = {"inventory_selection_id": selection["id"]}
    with pytest.raises(RuntimeError, match="simulated"):
        client.post("/api/runs", json=payload)
    monkeypatch.setattr(runs_routes, "enqueue_run", original)
    response = client.post("/api/runs", json=payload)
    assert response.status_code == 200, response.text
    assert len(list_queue_jobs()) == 1


def test_rebinding_is_explicit_and_invalidates_old_selection(inventory):
    store, root, sid = inventory
    (root / "doc.txt").write_text("source")
    store.new_scan(sid, ScanOptions(readers=1, isolate=False, show_hidden=True))
    work(store)
    selection = store.select(SelectionRequest())
    with pytest.raises(ValueError, match="exact registered"):
        store.rebind_source(sid, str(root / "other"))
    assert store.rebind_source(sid, str(root))["generation"] == 2
    with pytest.raises(ValueError, match="stale"):
        store.staged_members(selection["id"])
    assert store.summary(Filters())["files"] == 0
    store.new_scan(sid, ScanOptions(readers=1, isolate=False, show_hidden=True))
    work(store)
    assert store.summary(Filters())["files"] == 1


def test_pause_restart_resumes_checkpoint_without_duplicate_members(
    inventory, monkeypatch
):
    store, root, sid = inventory
    for n in range(12):
        (root / f"{n}.txt").write_text("data")
    from osii.volume import scanner

    monkeypatch.setattr(scanner, "BATCH_SIZE", 5)
    original = scanner._write_batch
    rid = store.new_scan(sid, ScanOptions(readers=1, isolate=False, show_hidden=True))

    def pause(*args):
        original(*args)
        store.control(rid, "pause")

    monkeypatch.setattr(scanner, "_write_batch", pause)
    assert work(store)["status"] == "paused"
    assert store.summary(Filters())["files"] == 5
    # A new store instance has no process-local scan state to recover.
    restarted = VolumeStore(store.path)
    restarted.initialize()
    monkeypatch.setattr(scanner, "_write_batch", original)
    restarted.control(rid, "resume")
    result = work(restarted)
    assert result["status"] == "done"
    assert result["observed_entries"] == 12
    assert restarted.select(SelectionRequest())["count"] == 12


def test_metadata_discovery_never_opens_contents(inventory, monkeypatch):
    store, root, sid = inventory
    (root / "doc.txt").write_text("Private original bytes")
    original = Path.open

    def no_originals(path, *args, **kwargs):
        if path.is_relative_to(root):
            raise AssertionError("Discovery opened a source document")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", no_originals)
    store.new_scan(sid, ScanOptions(isolate=False))
    assert work(store)["status"] == "done"
    assert store.summary(Filters())["files"] == 1


def test_scan_api_acknowledges_without_source_io_and_defaults_to_isolation(
    inventory, monkeypatch
):
    store, root, sid = inventory
    from osii.volume.api import create_app

    with TestClient(create_app(store.path)) as client:
        original = Path.stat

        def no_stat(path, *args, **kwargs):
            if path.is_relative_to(root):
                raise AssertionError("Scan acknowledgement accessed source")
            return original(path, *args, **kwargs)

        monkeypatch.setattr(Path, "stat", no_stat)
        response = client.post(f"/api/volume/sources/{sid}/scan", json={})
        assert response.status_code == 200, response.text
        options = json.loads(response.json()["payload"])
        assert options["isolate"] and options["readers"] == 2
        assert options["source_generation"] == 1
        assert client.get("/health").status_code == 200


def test_staged_time_budget_pause_and_resume_keep_completed_work(
    client, temp_osii_root, temp_data_root, monkeypatch
):
    for name in ("first.txt", "second.txt"):
        (temp_data_root / name).write_text(name)
    _, selection = stage_for_client(temp_osii_root, temp_data_root, monkeypatch)
    from osii.api import runs_routes
    from osii.domain.processing.jobs import (
        configure_job_store,
        claim_next_queue_job,
        get_run,
        pause_queue_job,
        control_run,
    )
    from osii.worker import execute_job

    configure_job_store(temp_osii_root)
    queued = client.post(
        "/api/runs",
        json={"inventory_selection_id": selection["id"], "max_processing_seconds": 1},
    )
    assert queued.status_code == 200
    original = runs_routes.dispatch_extract
    calls = []

    def dispatch(**kwargs):
        calls.append(kwargs["source_path"])
        kwargs["extractor_name"] = "native_text"
        return original(**kwargs)

    monkeypatch.setattr(runs_routes, "dispatch_extract", dispatch)
    clock = iter([0, 0, 2])
    monkeypatch.setattr(runs_routes, "monotonic", lambda: next(clock))
    job = claim_next_queue_job("test")
    execute_job(job)
    run = get_run(queued.json()["id"])
    assert run["status"] == "paused" and run["completed"] == 1
    pause_queue_job(job["id"])
    control_run(run["id"], "resume")
    monkeypatch.setattr(runs_routes, "monotonic", lambda: 0)
    execute_job(claim_next_queue_job("test"))
    run = get_run(run["id"])
    assert run["status"] == "done" and run["completed"] == 2
    assert len(calls) == 2  # The successful first file was not processed again.
