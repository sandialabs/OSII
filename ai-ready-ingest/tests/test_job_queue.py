from pathlib import Path
import sqlite3

from osii.domain.processing.jobs import (
    claim_next_queue_job,
    complete_queue_job,
    configure_job_store,
    control_run,
    create_run_record,
    get_run,
    list_queue_jobs,
    list_runs,
    recover_stale_queue_jobs,
    register_worker,
    save_run,
    unregister_worker,
    worker_status,
)


def test_sqlite_queue_claims_and_completes_a_durable_run(tmp_path: Path):
    osii_root = tmp_path / ".osii"
    shared_root = tmp_path / "shared"
    upload_root = tmp_path / "uploads"
    shared_root.mkdir()
    upload_root.mkdir()
    source = shared_root / "notes.txt"
    source.write_text("hello", encoding="utf-8")

    configure_job_store(osii_root)
    run = create_run_record([source], shared_root, upload_root, osii_root=osii_root)

    from osii.domain.processing.jobs import enqueue_run

    queued = enqueue_run(run["id"], {"resolved_files": [str(source)]})
    claimed = claim_next_queue_job()

    assert claimed is not None
    assert claimed["id"] == queued["id"]
    assert claimed["status"] == "running"
    assert get_run(run["id"])["total"] == 1

    complete_queue_job(claimed["id"])
    assert list_queue_jobs()[0]["status"] == "done"


def test_worker_error_becomes_a_visible_terminal_run(tmp_path: Path):
    osii_root = tmp_path / ".osii"
    shared_root = tmp_path / "shared"
    upload_root = tmp_path / "uploads"
    shared_root.mkdir()
    upload_root.mkdir()
    source = shared_root / "iris.csv"
    source.write_text("measurement,target\n1.0,0\n", encoding="utf-8")

    configure_job_store(osii_root)
    run = create_run_record([source], shared_root, upload_root, osii_root=osii_root)
    from osii.domain.processing.jobs import enqueue_run

    enqueue_run(run["id"], {"resolved_files": [str(source)]})
    claimed = claim_next_queue_job()
    assert claimed is not None
    complete_queue_job(claimed["id"], error="CSV processor connection refused")

    failed = get_run(run["id"])
    assert failed is not None
    assert failed["status"] == "error"
    assert failed["error"] == "CSV processor connection refused"
    assert "Worker error: CSV processor connection refused" in failed["logs"][-1]
    assert list_runs()[0]["status"] == "error"


def test_queue_can_pause_resume_and_cancel_without_losing_the_run(tmp_path: Path):
    osii_root = tmp_path / ".osii"
    shared_root = tmp_path / "shared"
    upload_root = tmp_path / "uploads"
    shared_root.mkdir()
    upload_root.mkdir()
    source = shared_root / "notes.txt"
    source.write_text("hello", encoding="utf-8")

    configure_job_store(osii_root)
    run = create_run_record([source], shared_root, upload_root, osii_root=osii_root)

    from osii.domain.processing.jobs import enqueue_run

    enqueue_run(run["id"], {"resolved_files": [str(source)]})
    paused = control_run(run["id"], "pause")
    assert paused["status"] == "paused"
    assert claim_next_queue_job() is None

    resumed = control_run(run["id"], "resume")
    assert resumed["status"] == "queued"
    claimed = claim_next_queue_job()
    assert claimed is not None

    cancelling = control_run(run["id"], "cancel")
    assert cancelling["status"] == "cancelling"
    assert get_run(run["id"])["control_state"] == "cancel_requested"


def test_worker_heartbeat_is_visible_to_the_api(tmp_path: Path):
    configure_job_store(tmp_path / ".osii")

    register_worker("worker-test")
    assert worker_status()["available"] is True
    unregister_worker("worker-test")
    assert worker_status()["available"] is False


def test_existing_windows_queue_database_is_migrated_in_place(tmp_path: Path):
    state_dir = tmp_path / ".osii" / "state"
    state_dir.mkdir(parents=True)
    database = state_dir / "jobs.sqlite3"
    with sqlite3.connect(database) as conn:
        conn.execute(
            """
            CREATE TABLE queue_jobs (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                error TEXT
            )
            """
        )

    configure_job_store(tmp_path / ".osii")

    with sqlite3.connect(database) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(queue_jobs)")}
        worker_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'workers'"
        ).fetchone()
    assert {"worker_id", "heartbeat_at"} <= columns
    assert worker_table == ("workers",)


def test_interrupted_running_job_returns_to_queue(tmp_path: Path):
    osii_root = tmp_path / ".osii"
    shared_root = tmp_path / "shared"
    upload_root = tmp_path / "uploads"
    shared_root.mkdir()
    upload_root.mkdir()
    source = shared_root / "notes.txt"
    source.write_text("hello", encoding="utf-8")
    configure_job_store(osii_root)
    run = create_run_record([source], shared_root, upload_root, osii_root=osii_root)
    from osii.domain.processing.jobs import enqueue_run

    enqueue_run(run["id"], {"resolved_files": [str(source)]})
    claimed = claim_next_queue_job("worker-that-disappeared")
    assert claimed is not None
    running = get_run(run["id"])
    running["status"] = "running"
    running["items"][0]["status"] = "running"
    save_run(running)

    recovered = recover_stale_queue_jobs()

    assert recovered == [run["id"]]
    assert list_queue_jobs()[0]["status"] == "queued"
    restored = get_run(run["id"])
    assert restored["status"] == "queued"
    assert restored["items"][0]["status"] == "pending"
    assert "returned to the queue" in restored["logs"][-1]


def test_failed_run_can_be_retried_without_repeating_completed_files(tmp_path: Path):
    osii_root = tmp_path / ".osii"
    shared_root = tmp_path / "shared"
    upload_root = tmp_path / "uploads"
    shared_root.mkdir()
    upload_root.mkdir()
    files = [shared_root / "done.txt", shared_root / "failed.txt"]
    for source in files:
        source.write_text(source.stem, encoding="utf-8")
    configure_job_store(osii_root)
    run = create_run_record(files, shared_root, upload_root, osii_root=osii_root)
    from osii.domain.processing.jobs import enqueue_run

    enqueue_run(run["id"], {"resolved_files": [str(path) for path in files]})
    claimed = claim_next_queue_job()
    run["status"] = "running"
    run["items"][0]["status"] = "done"
    run["items"][1]["status"] = "error"
    run["items"][1]["error"] = "temporary failure"
    run["completed"] = 1
    save_run(run)
    complete_queue_job(claimed["id"], error="temporary failure")
    assert get_run(run["id"])["status"] == "error"

    retried = control_run(run["id"], "retry")

    assert retried["status"] == "queued"
    restored = get_run(run["id"])
    assert restored["items"][0]["status"] == "done"
    assert restored["items"][1]["status"] == "pending"
    assert restored["completed"] == 1
