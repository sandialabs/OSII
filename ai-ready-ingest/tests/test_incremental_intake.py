import threading
from pathlib import Path

from osii.api import runs_routes
from osii.domain.processing.jobs import create_run_record, get_run
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

    def staged_dispatch(**kwargs):
        nonlocal dispatch_count
        dispatch_count += 1
        if dispatch_count == 2:
            second_started.set()
            if not release_second.wait(timeout=5):
                raise TimeoutError("test did not release the second extraction")
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
            "context": "",
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
