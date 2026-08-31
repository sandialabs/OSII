import json
import threading
from pathlib import Path

from osii.api import runs_routes
from osii.domain.processing.jobs import create_run_record, get_run, save_run
from osii.domain.scopes.membership import list_scope_file_ids
from osii.domain.storage.ids import compute_file_id


def test_completed_document_is_browsable_while_next_document_runs(
    temp_data_root: Path,
    temp_osii_root: Path,
    temp_upload_root: Path,
    monkeypatch,
):
    first = temp_data_root / "01-first.txt"
    second = temp_data_root / "02-second.txt"
    first.write_text("first document", encoding="utf-8")
    second.write_text("second document", encoding="utf-8")
    files = [first, second]

    run = create_run_record(
        files,
        temp_data_root,
        temp_upload_root,
        osii_root=temp_osii_root,
    )
    original_dispatch = runs_routes.dispatch_extract
    second_started = threading.Event()
    release_second = threading.Event()
    dispatch_count = 0
    expert_context = "REF files are controls; temperatures are ambient unless marked."
    observed_contexts: list[str | None] = []

    def staged_dispatch(**kwargs):
        nonlocal dispatch_count
        dispatch_count += 1
        observed_contexts.append(kwargs.get("expert_context"))
        if dispatch_count == 2:
            second_started.set()
            if not release_second.wait(timeout=5):
                raise TimeoutError("test did not release the second extraction")
        # This test isolates incremental commit behavior from the separately
        # contract-tested Processor API transport.
        kwargs["extractor_name"] = "native_text"
        return original_dispatch(**kwargs)

    monkeypatch.setattr(runs_routes, "dispatch_extract", staged_dispatch)
    routes_path = (
        Path(__file__).resolve().parents[1]
        / "config"
        / "extractor_routes_native.toml"
    )

    worker = threading.Thread(
        target=runs_routes.run_worker,
        kwargs={
            "run_id": run["id"],
            "resolved_files": files,
            "queue_items": [],
            "include_subfolders": True,
            "include_patterns": [],
            "exclude_patterns": [],
            "context": expert_context,
            "intake_name": "incremental-test",
            "data_volume_root": temp_data_root.parent,
            "osii_store": temp_osii_root,
            "shared_root": temp_data_root,
            "upload_root": temp_upload_root,
            "parser_routes_path": routes_path,
            "shared_root_host_path": str(temp_data_root),
            "synthesizer_name": None,
            "synthesizer_config": {},
        },
        daemon=True,
    )
    worker.start()

    try:
        assert second_started.wait(timeout=5)
        current_run = get_run(run["id"])
        assert current_run is not None
        assert current_run["completed"] == 1

        visible_ids = list_scope_file_ids(
            temp_osii_root,
            {"scope_type": "root"},
        )
        assert compute_file_id(first) in visible_ids
        assert compute_file_id(second) not in visible_ids
    finally:
        release_second.set()
        worker.join(timeout=5)

    assert not worker.is_alive()
    assert get_run(run["id"])["status"] == "done"
    assert observed_contexts == [expert_context, expert_context]

    manifest_path = next((temp_osii_root / "manifests").glob("intake-manifest-*.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["expert_context"] == expert_context


def test_run_pauses_between_files_and_records_file_timings(
    temp_data_root: Path,
    temp_osii_root: Path,
    temp_upload_root: Path,
    monkeypatch,
):
    first = temp_data_root / "01-first.txt"
    second = temp_data_root / "02-second.txt"
    first.write_text("first document", encoding="utf-8")
    second.write_text("second document", encoding="utf-8")
    files = [first, second]
    run = create_run_record(files, temp_data_root, temp_upload_root, osii_root=temp_osii_root)
    original_dispatch = runs_routes.dispatch_extract
    first_started = threading.Event()
    release_first = threading.Event()

    def staged_dispatch(**kwargs):
        kwargs["extractor_name"] = "native_text"
        if kwargs["source_path"] == first:
            first_started.set()
            assert release_first.wait(timeout=5)
        return original_dispatch(**kwargs)

    monkeypatch.setattr(runs_routes, "dispatch_extract", staged_dispatch)
    routes_path = Path(__file__).resolve().parents[1] / "config" / "extractor_routes_native.toml"
    worker_kwargs = {
        "run_id": run["id"],
        "resolved_files": files,
        "queue_items": [],
        "include_subfolders": True,
        "include_patterns": [],
        "exclude_patterns": [],
        "context": "",
        "intake_name": "pause-test",
        "data_volume_root": temp_data_root.parent,
        "osii_store": temp_osii_root,
        "shared_root": temp_data_root,
        "upload_root": temp_upload_root,
        "parser_routes_path": routes_path,
        "shared_root_host_path": str(temp_data_root),
        "synthesizer_name": None,
        "synthesizer_config": {},
    }
    worker = threading.Thread(target=runs_routes.run_worker, kwargs=worker_kwargs, daemon=True)
    worker.start()
    assert first_started.wait(timeout=5)
    current = get_run(run["id"])
    current["control_state"] = "pause_requested"
    current["status"] = "pausing"
    save_run(current)
    release_first.set()
    worker.join(timeout=5)

    paused = get_run(run["id"])
    assert paused["status"] == "paused"
    assert paused["completed"] == 1
    assert paused["items"][0]["duration_seconds"] >= 0
    assert paused["items"][0]["started_at"]
    assert paused["items"][0]["finished_at"]
    assert paused["items"][1]["status"] == "pending"

    paused["control_state"] = "running"
    paused["status"] = "queued"
    save_run(paused)
    runs_routes.run_worker(**worker_kwargs)
    completed = get_run(run["id"])
    assert completed["status"] == "done"
    assert completed["completed"] == 2
    assert completed["items"][1]["duration_seconds"] >= 0
