from __future__ import annotations

import base64
from pathlib import Path
import sqlite3
import threading
import time

from fastapi.testclient import TestClient
import pytest

from osii.processor_sdk.models import (
    Capability,
    ExtractionResponse,
    ProcessorDescriptor,
    ProcessorKind,
    TextSegment,
    SynthesisResponse,
    ProvenanceRef,
)
from osii.volume.api import create_app
from osii.volume.models import Filters, ProcessRequest, SelectionRequest, ScanOptions
from osii.volume.store import VolumeStore
from osii.volume.worker import execute


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    store = VolumeStore(tmp_path / "volume.sqlite3")
    store.initialize()
    source = store.register_source(root)
    return store, root, source["id"]


def work(store, factory=None):
    job = store.claim("test-worker")
    assert job
    execute(store, job, "test-worker", threading.Event(), factory)
    return store.run(job["id"])


def scan(store, source):
    store.new_scan(source, ScanOptions(readers=1, isolate=False, show_hidden=True))
    return work(store)


class Extractor:
    calls = 0
    descriptor_value = ProcessorDescriptor(
        name="local.native-text",
        version="1",
        display_name="Test",
        description="Test",
        kind=ProcessorKind.EXTRACTOR,
        capabilities=Capability(),
    )

    def __init__(self, *args):
        pass

    def descriptor(self):
        return self.descriptor_value

    def extract(self, request):
        type(self).calls += 1
        text = base64.b64decode(request.document.content_base64).decode()
        return ExtractionResponse(
            request_id=request.request_id,
            processor=self.descriptor_value,
            segments=[TextSegment(id="s1", text=text, source_origin={"page": 1})]
            if text
            else [],
        )


class Synthesizer(Extractor):
    descriptor_value = ProcessorDescriptor(
        name="test.synthesizer",
        version="1",
        display_name="Test",
        description="Test",
        kind=ProcessorKind.SYNTHESIZER,
        capabilities=Capability(),
    )

    def synthesize(self, request):
        document = request.scope.documents[0]
        return SynthesisResponse(
            request_id=request.request_id,
            processor=self.descriptor_value,
            markdown=document.text,
            citations=[
                ProvenanceRef(
                    file_id=document.file_id, char_start=0, char_end=len(document.text)
                )
            ],
        )


def extract_all(store):
    selected = store.select(SelectionRequest(max_files=1000))
    store.new_processing(ProcessRequest(selection_id=selected["id"]))
    result = work(store, Extractor)
    assert result["status"] == "done", result
    return selected, result


def test_inventory_never_reads_contents_or_creates_sidecars(library, monkeypatch):
    store, root, source = library
    (root / "nested").mkdir()
    (root / "nested" / "Résumé.TXT").write_text("source evidence")
    (root / ".hidden").write_text("hidden source")
    with (root / "large.bin").open("wb") as stream:
        stream.truncate(3 * 1024**3)
    monkeypatch.setattr(
        Path, "read_bytes", lambda *_: pytest.fail("Inventory read content")
    )
    monkeypatch.setattr(
        Path, "read_text", lambda *_a, **_k: pytest.fail("Inventory read content")
    )
    result = scan(store, source)
    assert result["status"] == "done"
    summary = store.summary(Filters())
    assert summary["files"] == 3
    assert summary["bytes"] > 2**31
    assert not list(root.rglob(".osii"))
    assert {r["path"] for r in store.entries(Filters())["items"]} == {
        ".hidden",
        "large.bin",
        "nested/Résumé.TXT",
    }


def test_inventory_is_available_in_normal_local_app_without_user_auth(
    test_app, monkeypatch
):
    from osii.main import inventory_app
    from osii.volume.store import database_path

    monkeypatch.delenv("OSII_INVENTORY_DB", raising=False)
    monkeypatch.delenv("OSII_VOLUME_DB", raising=False)
    root = test_app.state.shared_volume_root
    (root / "report.txt").write_text(
        "This content should not be extracted by a metadata scan."
    )
    marker = test_app.state.osii_root / "preserve-existing-library.txt"
    marker.write_text("existing sidecar evidence")
    with TestClient(test_app) as client:
        runtime = client.get("/api/runtime")
        assert runtime.status_code == 200
        assert runtime.json()["storage_mode"] == "local"
        assert runtime.json()["user_authentication"] is False
        assert client.post("/api/auth/login", json={}).status_code == 404
        assert client.get("/api/auth/me").status_code == 404
        sources = client.get("/api/volume/sources").json()["items"]
        source = next(s for s in sources if s["root"] == str(root))
        response = client.post(f"/api/volume/sources/{source['id']}/scan")
        assert response.status_code == 200
        store = inventory_app.state.volume_store
        assert store.path == database_path(test_app.state.osii_root)
        assert work(store)["status"] == "done"
        entries = client.get("/api/volume/entries").json()["items"]
        assert len(entries) == 1 and entries[0]["path"] == "report.txt"
        assert entries[0]["extraction_id"] is None
        assert client.get("/api/browse").status_code == 200
        assert marker.read_text() == "existing sidecar evidence"
        assert not (root / ".osii").exists()
    with TestClient(test_app) as client:
        assert client.get("/api/volume/summary").json()["files"] == 1
        assert marker.read_text() == "existing sidecar evidence"


def test_inventory_database_path_supports_local_default_and_existing_pilot(
    monkeypatch, tmp_path
):
    from osii.volume.store import database_path

    monkeypatch.delenv("OSII_INVENTORY_DB", raising=False)
    monkeypatch.delenv("OSII_VOLUME_DB", raising=False)
    root = tmp_path / ".osii"
    monkeypatch.setenv("OSII_ROOT", str(root))
    assert database_path() == root / "state" / "inventory.sqlite3"
    old = tmp_path / "previous-volume.sqlite3"
    monkeypatch.setenv("OSII_VOLUME_DB", str(old))
    assert database_path() == old
    current = tmp_path / "current-inventory.sqlite3"
    monkeypatch.setenv("OSII_INVENTORY_DB", str(current))
    assert database_path() == current


def test_scan_refresh_staleness_missing_subtree_and_duplicate_locations(library):
    store, root, source = library
    folder = root / "folder"
    folder.mkdir()
    (folder / "first.txt").write_text("shared evidence")
    (root / "copy.txt").write_text("shared evidence")
    scan(store, source)
    Extractor.calls = 0
    extract_all(store)
    assert Extractor.calls == 1
    assert len(store.search("evidence")["items"]) == 2
    old = store.entries(Filters())["items"]
    scan(store, source)
    assert [e["revision"] for e in store.entries(Filters())["items"]] == [
        e["revision"] for e in old
    ]
    (folder / "first.txt").unlink()
    folder.rmdir()
    (root / "copy.txt").write_text("new evidence and facts")
    scan(store, source)
    assert store.summary(Filters())["files"] == 1
    assert store.search("evidence")["items"] == []
    with store.connect() as conn:
        assert conn.execute("SELECT count(*) FROM extractions").fetchone()[0] == 1
        assert (
            conn.execute(
                "SELECT status FROM entries WHERE path='folder/first.txt'"
            ).fetchone()[0]
            == "missing"
        )
        assert conn.execute("SELECT count(*) FROM entry_extractions").fetchone()[0] == 2


def test_disconnect_preserves_inventory_and_resume(library, monkeypatch):
    store, root, source = library
    (root / "a.txt").write_text("alpha")
    scan(store, source)
    import osii.domain.processing.directory_scan as scanner

    real_scandir = scanner.os.scandir

    def unavailable(path):
        raise PermissionError("denied")

    monkeypatch.setattr(scanner.os, "scandir", unavailable)
    result = scan(store, source)
    assert result["status"] == "error"
    assert store.summary(Filters())["files"] == 1
    assert store.events(result["id"])
    monkeypatch.setattr(scanner.os, "scandir", real_scandir)
    store.control(result["id"], "resume")
    assert work(store)["status"] == "done"


def test_restart_replays_large_directory_without_false_absence(library, monkeypatch):
    store, root, source = library
    for i in range(12):
        (root / f"{i}.txt").write_text(str(i))
    import osii.volume.scanner as scanner

    monkeypatch.setattr(scanner, "BATCH_SIZE", 3)
    original = scanner._write_batch
    stopping = threading.Event()

    def interrupted(*args):
        original(*args)
        stopping.set()

    monkeypatch.setattr(scanner, "_write_batch", interrupted)
    rid = store.new_scan(
        source, ScanOptions(readers=1, isolate=False, show_hidden=True)
    )
    execute(store, store.claim("test-worker"), "test-worker", stopping)
    assert store.run(rid)["status"] == "queued"
    assert store.summary(Filters())["files"] == 3
    # A file seen during the failed attempt disappears before replay.
    with store.connect() as conn:
        seen = conn.execute("SELECT path FROM entries LIMIT 1").fetchone()[0]
    (root / seen).unlink()
    monkeypatch.setattr(scanner, "_write_batch", original)
    assert work(store)["status"] == "done"
    assert store.summary(Filters())["files"] == 11
    with store.connect() as conn:
        assert (
            conn.execute("SELECT status FROM entries WHERE path=?", (seen,)).fetchone()[
                0
            ]
            == "missing"
        )


def test_expired_lease_prevents_old_worker_commit(library):
    store, root, source = library
    (root / "a.txt").write_text("alpha")
    rid = store.new_scan(
        source, ScanOptions(readers=1, isolate=False, show_hidden=True)
    )
    old = store.claim("old")
    assert store.claim("other") is None
    with store.connect() as conn:
        conn.execute("UPDATE runs SET lease_until=0 WHERE id=?", (rid,))
    new = store.claim("new")
    execute(store, old, "old", threading.Event())
    assert store.summary(Filters())["files"] == 0
    execute(store, new, "new", threading.Event())
    assert store.run(rid)["status"] == "done"


def test_selection_filters_sampling_budgets_and_stale_snapshot(library):
    store, root, source = library
    for suffix in ("txt", "csv"):
        for index in range(10):
            (root / f"{index}.{suffix}").write_text("abc")
    scan(store, source)
    first = store.select(SelectionRequest(sample=True, seed="repeat", max_bytes=9))
    second = store.select(SelectionRequest(sample=True, seed="repeat", max_bytes=9))

    def ids(selection):
        return [
            entry["id"] for entry in store.selection_entries(selection["id"])["items"]
        ]

    assert ids(first) == ids(second)
    assert first["bytes"] <= 9 and first["count"] == 3
    assert (
        len({e["suffix"] for e in store.selection_entries(first["id"])["items"]}) == 2
    )
    selection = store.select(
        SelectionRequest(filters=Filters(suffix="txt"), max_files=3)
    )
    member = store.selection_entries(selection["id"])["items"][0]
    (root / member["path"]).write_text("changed")
    scan(store, source)
    store.new_processing(ProcessRequest(selection_id=selection["id"]))
    result = work(store, Extractor)
    assert result["status"] == "error"
    assert store.report(result["id"])["metrics"]["errors"] == 1


def test_source_change_during_extraction_never_publishes(library):
    store, root, source = library
    path = root / "a.txt"
    path.write_text("before")
    scan(store, source)
    selected = store.select(SelectionRequest())

    class Changing(Extractor):
        def extract(self, request):
            response = super().extract(request)
            path.write_text("after change")
            return response

    store.new_processing(ProcessRequest(selection_id=selected["id"]))
    assert work(store, Changing)["status"] == "error"
    with store.connect() as conn:
        assert conn.execute("SELECT count(*) FROM extractions").fetchone()[0] == 0


def test_synthesis_failure_does_not_remove_text_and_products_become_stale(library):
    store, root, source = library
    path = root / "a.txt"
    path.write_text("grounded evidence")
    scan(store, source)
    selection, extracted = extract_all(store)
    store.new_processing(
        ProcessRequest(
            selection_id=selection["id"],
            stage="synthesize",
            endpoint="http://localhost:8093",
        )
    )
    assert work(store, Synthesizer)["status"] == "done"
    entry = store.entries(Filters())["items"][0]
    assert store.document(entry["id"])["products"][0]["stale"] == 0

    class Failing(Synthesizer):
        def synthesize(self, request):
            raise RuntimeError("private provider failure body")

    store.new_processing(
        ProcessRequest(selection_id=selection["id"], stage="synthesize")
    )
    failure = work(store, Failing)
    assert failure["status"] == "error"
    assert "private" not in str(store.events(failure["id"]))
    assert store.search("grounded")["items"]
    path.write_text("new source content")
    scan(store, source)
    assert store.document(entry["id"])["products"][0]["stale"] == 1
    assert store.document(entry["id"])["history"]


def test_no_text_is_recorded_as_ocr_candidate(library):
    store, root, source = library
    (root / "empty.txt").write_text("")
    scan(store, source)
    _, result = extract_all(store)
    assert store.report(result["id"])["metrics"]["needs_ocr"] == 1


def test_symlinks_and_directory_replaced_by_file(library):
    store, root, source = library
    folder = root / "folder"
    folder.mkdir()
    (folder / "a.txt").write_text("old")
    try:
        (root / "link").symlink_to(root, target_is_directory=True)
    except OSError:
        pytest.skip("Symlinks unavailable")
    scan(store, source)
    assert store.summary(Filters())["files"] == 1
    (folder / "a.txt").unlink()
    folder.rmdir()
    folder.write_text("file now")
    assert scan(store, source)["status"] == "done"
    assert store.summary(Filters())["files"] == 1
    with store.connect() as conn:
        assert (
            conn.execute(
                "SELECT status FROM entries WHERE path='folder/a.txt'"
            ).fetchone()[0]
            == "missing"
        )


def test_root_identity_change_preserves_previous_inventory(library):
    store, root, source = library
    (root / "a.txt").write_text("alpha")
    scan(store, source)
    root.rename(root.with_name("old-source"))
    root.mkdir()
    assert scan(store, source)["status"] == "error"
    assert store.summary(Filters())["files"] == 1


def test_pause_cancel_and_resume(library):
    store, root, source = library
    rid = store.new_scan(
        source, ScanOptions(readers=1, isolate=False, show_hidden=True)
    )
    store.control(rid, "pause")
    assert store.claim("worker") is None
    store.control(rid, "resume")
    assert work(store)["status"] == "done"
    rid = store.new_scan(
        source, ScanOptions(readers=1, isolate=False, show_hidden=True)
    )
    store.control(rid, "cancel")
    assert store.claim("worker") is None


def test_backup_restore_and_rebuild_preserve_evidence(library, tmp_path):
    store, root, source = library
    (root / "a.txt").write_text("backup evidence")
    scan(store, source)
    extract_all(store)
    backup = tmp_path / "backup.sqlite3"
    store.backup(backup)
    restored = VolumeStore(backup)
    restored.initialize()
    restored.rebuild_search()
    assert len(restored.search("backup")["items"]) == 1
    with pytest.raises(ValueError):
        store.backup(backup)
    with pytest.raises(ValueError):
        store.register_source(tmp_path)
    with pytest.raises(ValueError):
        store.backup(root / "backup.sqlite3")


def test_database_schema_never_silently_rebuilds(tmp_path):
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE evidence(value TEXT)")
        conn.execute("INSERT INTO evidence VALUES('keep')")
    with pytest.raises(ValueError):
        VolumeStore(path).initialize()
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT * FROM evidence").fetchone()[0] == "keep"


def test_api_uses_volume_store_and_cursor_pages(library, monkeypatch):
    store, root, source = library
    monkeypatch.delenv("SHARED_VOLUME_ROOT", raising=False)
    (root / "a.txt").write_text("alpha")
    (root / "b.txt").write_text("beta")
    scan(store, source)
    with TestClient(create_app(store.path)) as client:
        assert client.get("/api/runtime").json()["storage_mode"] == "local"
        page = client.get("/api/volume/entries?limit=1").json()
        assert len(page["items"]) == 1
        assert (
            client.get(
                f"/api/volume/entries?cursor={page['next_cursor']}&limit=1"
            ).json()["items"][0]["id"]
            != page["items"][0]["id"]
        )
        assert client.get("/api/volume/entries?limit=1000").status_code == 422
        assert (
            client.post("/api/volume/selections", json={"max_files": 1}).json()["count"]
            == 1
        )
        assert client.get("/api/volume/search?q=%22").status_code == 422
        assert (
            client.get(
                "/api/volume/sources", headers={"Origin": "https://untrusted.example"}
            ).status_code
            == 403
        )
        assert client.get("/api/volume/entries/9999").status_code == 404
        assert client.get("/api/catalog/rebuild").status_code == 404


def test_disk_failure_rolls_back_current_batch(library, monkeypatch):
    store, root, source = library
    (root / "a.txt").write_text("alpha")
    import osii.volume.scanner as scanner

    original = scanner._write_batch

    def disk_full(*args):
        with store.connect() as conn:
            conn.execute(
                "INSERT INTO events(run_id,created,message) VALUES(?,?,?)",
                (args[1]["id"], time.time(), "transaction not committed"),
            )
            raise sqlite3.OperationalError("database or disk is full")

    monkeypatch.setattr(scanner, "_write_batch", disk_full)
    result = scan(store, source)
    assert result["status"] == "error"
    assert store.summary(Filters())["files"] == 0
    assert all(
        e["message"] != "transaction not committed" for e in store.events(result["id"])
    )
    monkeypatch.setattr(scanner, "_write_batch", original)
    store.control(result["id"], "resume")
    assert work(store)["status"] == "done"


def test_concurrent_initialization_is_atomic(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    path = tmp_path / "concurrent.sqlite3"
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: VolumeStore(path).initialize(), range(4)))
    assert VolumeStore(path).sources() == []


def test_processor_configuration_rejected_before_reading_sources(library, monkeypatch):
    store, root, source = library
    (root / "a.txt").write_text("alpha")
    scan(store, source)
    selected = store.select(SelectionRequest())

    class Configured(Extractor):
        descriptor_value = Extractor.descriptor_value.model_copy(
            update={
                "config_schema": {
                    "type": "object",
                    "properties": {"size": {"type": "integer", "minimum": 10}},
                    "additionalProperties": False,
                }
            }
        )

    import osii.volume.processing as processing

    monkeypatch.setattr(
        processing, "read_source", lambda *_: pytest.fail("Invalid config read source")
    )
    store.new_processing(
        ProcessRequest(selection_id=selected["id"], config={"size": 1})
    )
    result = work(store, Configured)
    assert result["status"] == "error"
    assert "schema" in result["error"]


def test_verified_original_and_historical_inspection(library, monkeypatch):
    store, root, source = library
    monkeypatch.delenv("SHARED_VOLUME_ROOT", raising=False)
    path = root / "a.txt"
    path.write_text("first evidence")
    scan(store, source)
    extract_all(store)
    entry = store.entries(Filters())["items"][0]
    with TestClient(create_app(store.path)) as client:
        assert (
            client.get(f"/api/volume/entries/{entry['id']}/original").content
            == b"first evidence"
        )
        path.write_text("second evidence")
        assert (
            client.get(f"/api/volume/entries/{entry['id']}/original").status_code == 409
        )
        scan(store, source)
        assert (
            client.get(
                f"/api/volume/entries/{entry['id']}/extractions/{entry['extraction_id']}"
            ).json()["text"]
            == "first evidence"
        )
        assert store.summary(Filters(text_state="metadata_only"))["files"] == 1


def test_content_reuse_respects_format_and_arbitrary_processor_metadata(library):
    store, root, source = library
    (root / "a.txt").write_text("same bytes")
    (root / "b.csv").write_text("same bytes")
    scan(store, source)
    Extractor.calls = 0
    selected, _ = extract_all(store)
    assert Extractor.calls == 2  # Same bytes, different parser format.

    class MetadataAware(Extractor):
        calls = 0
        descriptor_value = Extractor.descriptor_value.model_copy(
            update={"name": "custom.metadata-aware"}
        )

    store.new_processing(ProcessRequest(selection_id=selected["id"]))
    assert work(store, MetadataAware)["status"] == "done"
    assert MetadataAware.calls == 2


def test_bounded_response_rejects_oversized_processor_output(monkeypatch):
    from io import BytesIO
    from osii.volume.processing import BoundedClient
    import urllib.request

    monkeypatch.setattr(
        urllib.request, "urlopen", lambda *_a, **_k: BytesIO(b"x" * 1025)
    )
    with pytest.raises(ValueError, match="size limit"):
        BoundedClient("http://localhost", 1024).descriptor()


def test_cli_selection_export_and_backup(library, tmp_path, capsys):
    import json
    from osii.volume.__main__ import main

    store, root, source = library
    (root / "a.txt").write_text("CLI evidence")
    scan(store, source)
    prefix = ["--db", str(store.path)]
    assert main([*prefix, "select", "--text-state", "metadata_only", "--sample"]) == 0
    assert json.loads(capsys.readouterr().out)["count"] == 1
    output = tmp_path / "inventory.jsonl"
    assert main([*prefix, "export", str(output)]) == 0
    assert json.loads(output.read_text())["path"] == "a.txt"
    assert main([*prefix, "export", str(output)]) == 1
    assert main([*prefix, "backup", str(tmp_path / "backup.sqlite3")]) == 0


def test_explicit_selection_is_exact_and_does_not_grow(library):
    store, root, source_id = library
    for name in ("one.txt", "two.txt", "three.txt"):
        (root / name).write_text(name)
    scan(store, source_id)
    rows = store.entries(Filters(source_id=source_id))["items"]
    ids = [rows[0]["id"], rows[2]["id"]]
    selection = store.select(
        SelectionRequest(filters=Filters(source_id=source_id), entry_ids=ids)
    )
    assert selection["count"] == 2
    (root / "later.txt").write_text("later")
    scan(store, source_id)
    assert {
        item["id"] for item in store.selection_entries(selection["id"])["items"]
    } == set(ids)
    assert store.selection(selection["id"])["count"] == 2


def test_explicit_selection_rejects_missing_cross_source_and_over_budget(
    library, tmp_path
):
    store, root, source_id = library
    (root / "one.txt").write_text("one")
    scan(store, source_id)
    entry = store.entries(Filters(source_id=source_id))["items"][0]
    before = len(store.selections())
    for ids, budget in [([entry["id"], 999999], 1024), ([entry["id"]], 1)]:
        with pytest.raises(ValueError, match="Some selected files"):
            store.select(
                SelectionRequest(
                    filters=Filters(source_id=source_id),
                    entry_ids=ids,
                    max_bytes=budget,
                )
            )
    assert len(store.selections()) == before  # Invalid selection creation rolls back.
    other = tmp_path / "other"
    other.mkdir()
    other_id = store.register_source(other)["id"]
    with pytest.raises(ValueError, match="Some selected files"):
        store.select(
            SelectionRequest(
                filters=Filters(source_id=other_id), entry_ids=[entry["id"]]
            )
        )


def test_explicit_selection_during_scan_requires_acknowledgement(library):
    store, root, source_id = library
    (root / "one.txt").write_text("one")
    scan(store, source_id)
    entry = store.entries(Filters(source_id=source_id))["items"][0]
    run_id = store.new_scan(source_id, ScanOptions(isolate=False))
    with store.connect() as conn:
        conn.execute(
            "UPDATE entries SET scan_run_id=? WHERE id=?", (run_id, entry["id"])
        )
    request = SelectionRequest(
        filters=Filters(source_id=source_id), entry_ids=[entry["id"]]
    )
    with pytest.raises(ValueError, match="incomplete"):
        store.select(request)
    request.allow_partial = True
    selection = store.select(request)
    assert selection["count"] == 1
    reloaded = VolumeStore(store.path)
    assert reloaded.selection(selection["id"])["count"] == 1
    reloaded.control(run_id, "pause")
    reloaded.control(run_id, "resume")
    assert reloaded.run(run_id)["status"] == "queued"


def test_recent_run_listing_preserves_legacy_order(library):
    store, root, source_id = library
    for _ in range(3):
        run_id = store.new_scan(source_id)
        store.control(run_id, "cancel")
    legacy = store.runs()
    assert [r["id"] for r in legacy] == sorted(r["id"] for r in legacy)
    assert [r["id"] for r in store.runs(recent=True)] == [
        r["id"] for r in reversed(legacy)
    ]
    assert len(store.runs(recent=True, before=legacy[-1]["id"])) == 2


def test_changed_mount_is_reported_for_contextual_recovery(library):
    store, root, source_id = library
    with store.connect() as conn:
        conn.execute("UPDATE sources SET inode='changed' WHERE id=?", (source_id,))
    result = scan(store, source_id)
    assert result["status"] == "error"
    assert result["issue_code"] == "identity_changed"
    assert store.runs(recent=True)[0]["issue_code"] == "identity_changed"


def test_registered_mount_does_not_block_startup_or_trigger_source_io(library, monkeypatch):
    store, root, source_id = library
    with store.connect() as conn:
        conn.execute("UPDATE sources SET inode='previous-mount' WHERE id=?", (source_id,))
    original = Path.is_dir
    def no_source_probe(path):
        if path == root:
            raise AssertionError("Existing mounts must not be probed during inventory startup")
        return original(path)
    monkeypatch.setattr(Path, "is_dir", no_source_probe)
    app = create_app(store.path)
    app.state.source_root = str(root)
    with TestClient(app) as client:
        response = client.get("/api/volume/sources")
        assert response.status_code == 200
        assert response.json()["items"][0]["inode"] == "previous-mount"
    assert store.source(source_id)["inode"] == "previous-mount"
