from pathlib import Path

from osii.domain.processing.jobs import (
    claim_next_queue_job,
    complete_queue_job,
    configure_job_store,
    control_run,
    create_run_record,
    get_run,
    list_queue_jobs,
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
