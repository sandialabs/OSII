"""Selected embeddings: failure recovery, vector preservation, and immutable snapshots."""

import hashlib
import json
from pathlib import Path
import sqlite3

import faiss
import numpy as np
import pytest

from osii.domain.storage.embedding_snapshot import active_snapshot, embedding_writer
from osii.domain.storage.objects import (
    write_meta_toml,
    write_text_file,
    write_provenance_toml,
)
from osii.domain.storage.store import ensure_osii_store_layout
from osii.indexing import incremental
from osii.indexing.common import ensure_embeddings_dir


class Client:
    base_url = "http://test-embedding.local/v1"
    descriptor = {"version": "1"}
    semantic = True
    model_digest = "digest-v1"
    model_name = "test-model"

    def __init__(self):
        self.calls = []
        self.bad = set()
        self.dimension = 3
        self.crash_on = None

    def embed(self, *, model, texts):
        assert model == "test-model"
        self.calls.append(list(texts))
        if self.crash_on and self.crash_on in texts:
            raise KeyboardInterrupt("worker terminated")
        if any(text in self.bad for text in texts):
            raise ValueError("bad input")
        return [
            [
                1 + hashlib.sha256(text.encode()).digest()[i]
                for i in range(self.dimension)
            ]
            for text in texts
        ]


def document(root, name, text):
    file_id = "sha256-" + hashlib.sha256(name.encode()).hexdigest()
    write_meta_toml(
        root,
        file_id,
        name,
        name,
        "text/plain",
        len(text),
        "2026-11-09T00:00:00Z",
        file_id[7:],
    )
    write_text_file(root, file_id, text)
    write_provenance_toml(
        root,
        file_id,
        "test",
        status="done",
        extractor_name="test",
        extractor_version="1",
    )
    return file_id


@pytest.fixture
def library(tmp_path, monkeypatch):
    root = tmp_path / ".osii"
    ensure_osii_store_layout(root)
    client = Client()
    from osii.configuration import save_models_config

    monkeypatch.setenv("OSII_ROOT", str(root))
    save_models_config(
        {
            "version": 1,
            "defaults": {"embedding": "test"},
            "models": {
                "test": {
                    "type": "openai-compatible",
                    "model": "test-model",
                    "base_url": client.base_url,
                    "capabilities": ["embedding"],
                    "enabled": True,
                }
            },
        }
    )
    monkeypatch.setattr(incremental, "create_embedding_client", lambda: client)
    monkeypatch.setattr("osii.indexing.common.time.sleep", lambda _: None)
    return root, client


def embed(root, ids, **kwargs):
    return incremental.embed_selected_documents(
        root, ids, model="test-model", chunking_method="paragraph", **kwargs
    )


def published(root):
    snapshot = active_snapshot(ensure_embeddings_dir(root))
    index = faiss.read_index(str(snapshot / "segments.faiss"))
    rows = [
        json.loads(line)
        for line in (snapshot / "segments.mapping.jsonl").read_text().splitlines()
    ]
    return (
        snapshot,
        rows,
        {
            row.get("embedding_key", f"legacy-{i}"): index.reconstruct(i)
            for i, row in enumerate(rows)
        },
    )


def test_only_selected_text_is_read_and_unrelated_vectors_are_preserved(
    library, monkeypatch
):
    root, client = library
    first = document(root, "first.txt", "First document")
    second = document(root, "second.txt", "Second document")
    unrelated = document(root, "unrelated.txt", "Never selected")
    embed(root, [first])
    old_snapshot, old_rows, old_vectors = published(root)
    original = Path.open

    def selected_only(path, *args, **kwargs):
        if path.name in {"text.txt", "edited_text.json", "manifest.jsonl"} and (
            root / "objects" / unrelated in path.parents
            or root / "objects" / first in path.parents
        ):
            raise AssertionError("Read unselected document sidecars")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", selected_only)
    report = embed(root, [second])
    assert report["completed_documents"] == 1
    assert client.calls == [["First document"], ["Second document"]]
    _, rows, vectors = published(root)
    assert {row["file_id"] for row in rows} == {first, second}
    assert len(rows) == 2
    for key, vector in old_vectors.items():
        np.testing.assert_array_equal(vectors[key], vector)
    assert old_snapshot.exists()  # Readers with an earlier snapshot can finish.


def test_retry_skips_completed_documents_and_successes_after_failed_middle_chunk(
    library,
):
    root, client = library
    first = document(root, "first.txt", "Done first")
    mixed = document(root, "mixed.txt", "Before failure\n\nBad middle\n\nAfter failure")
    last = document(root, "last.txt", "Done last")
    client.bad = {"Bad middle"}
    with pytest.raises(incremental.IncrementalEmbeddingError) as error:
        embed(root, [first, mixed, last], batch_size=1)
    assert error.value.report["completed_documents"] == 2
    assert set(error.value.report["failures"]) == {mixed}
    _, rows, old = published(root)
    assert {row["file_id"] for row in rows} == {first, last}
    client.bad.clear()
    client.calls.clear()
    report = embed(root, [first, mixed, last], batch_size=1)
    assert report["completed_documents"] == 3
    assert client.calls == [["Bad middle"]]  # No max-ordinal resume that skips a hole.
    _, rows, vectors = published(root)
    assert len(rows) == 5
    for key, vector in old.items():
        np.testing.assert_array_equal(vectors[key], vector)
    client.calls.clear()
    embed(root, [first, mixed, last])
    assert client.calls == []


def test_worker_exit_after_commit_keeps_chunks_without_repeating_requests(library):
    root, client = library
    file_id = document(root, "three.txt", "First chunk\n\nSecond chunk\n\nThird chunk")
    count = 0

    def crash(report):
        nonlocal count
        count += 1
        if report["embedded_chunks"] == 1:
            raise KeyboardInterrupt("exited after durable response")

    with pytest.raises(KeyboardInterrupt):
        embed(root, [file_id], batch_size=1, on_progress=crash)
    client.calls.clear()
    embed(root, [file_id], batch_size=1)
    assert client.calls == [["Second chunk"], ["Third chunk"]]
    assert len(published(root)[1]) == 3


def test_failed_publication_preserves_old_snapshot_and_retry_uses_cached_vectors(
    library, monkeypatch
):
    root, client = library
    first = document(root, "first.txt", "Existing")
    second = document(root, "second.txt", "New")
    embed(root, [first])
    old_snapshot, _, vectors = published(root)
    original = incremental.publish_snapshot

    def crash(*args):
        raise OSError("disk full before pointer replacement")

    monkeypatch.setattr(incremental, "publish_snapshot", crash)
    with pytest.raises(OSError):
        embed(root, [second])
    assert published(root)[0] == old_snapshot
    monkeypatch.setattr(incremental, "publish_snapshot", original)
    client.calls.clear()
    embed(root, [second])
    assert client.calls == []
    assert len(published(root)[1]) == 2


def test_changed_text_replaces_only_selected_document_and_reuses_matching_chunks(
    library,
):
    root, client = library
    first = document(root, "first.txt", "Keep this chunk\n\nReplace this chunk")
    second = document(root, "second.txt", "Unchanged document")
    embed(root, [first, second])
    _, old_rows, old_vectors = published(root)
    from osii.domain.artifacts.extraction_variants import primary_extraction_dir

    (primary_extraction_dir(root, first) / "text.txt").write_text(
        "Keep this chunk\n\nNew replacement chunk"
    )
    client.calls.clear()
    embed(root, [first])
    assert client.calls == [["New replacement chunk"]]
    _, rows, vectors = published(root)
    assert len(rows) == 3
    second_key = next(
        row["embedding_key"] for row in old_rows if row["file_id"] == second
    )
    np.testing.assert_array_equal(vectors[second_key], old_vectors[second_key])


def test_connection_or_dimensions_cannot_mix_with_existing_vectors(library):
    root, client = library
    first = document(root, "first.txt", "Existing")
    second = document(root, "second.txt", "New")
    embed(root, [first])
    snapshot = published(root)[0]
    client.dimension = 2
    with pytest.raises(incremental.IncompatibleIndexError, match="dimensions"):
        embed(root, [second])
    assert published(root)[0] == snapshot
    client.dimension = 3
    client.base_url = "http://different.example/v1"
    client.calls.clear()
    with pytest.raises(incremental.IncompatibleIndexError, match="connection"):
        embed(root, [second])
    assert client.calls == []


def test_pause_retains_partial_document_chunks_and_preserves_previous_vectors(library):
    root, client = library
    first = document(root, "first.txt", "Already saved")
    second = document(root, "second.txt", "Pending one\n\nPending two")
    embed(root, [first])
    report = embed(
        root,
        [second],
        batch_size=1,
        should_stop=lambda: client.calls[-1] == ["Pending one"],
    )
    assert report["paused"] is True
    assert len(published(root)[1]) == 1
    client.calls.clear()
    embed(root, [second], batch_size=1)
    assert client.calls == [["Pending two"]]


def test_second_writer_fails_promptly(library):
    root, _ = library
    with embedding_writer(root):
        with pytest.raises(RuntimeError, match="Another embedding writer"):
            with embedding_writer(root):
                pass


def test_intake_embedding_retry_does_not_repeat_file_processing(
    library, tmp_path, monkeypatch
):
    root, client = library
    first = document(root, "first.txt", "Already embedded")
    second = document(root, "second.txt", "Temporarily rejected")
    from osii.api import runs_routes
    from osii.domain.processing.jobs import (
        create_run_record,
        save_run,
        enqueue_run,
        claim_next_queue_job,
        complete_queue_job,
        control_run,
        get_run,
    )
    from osii.worker import execute_job

    originals = tmp_path / "originals"
    originals.mkdir()
    paths = [originals / "first.txt", originals / "second.txt"]
    run = create_run_record(paths, originals, tmp_path / "uploads", osii_root=root)
    for item, file_id in zip(run["items"], [first, second]):
        item.update(status="done", file_id=file_id)
    run.update(
        status="queued", file_processing_status="done", workflow="intake", completed=2
    )
    save_run(run)
    enqueue_run(
        run["id"],
        {
            "osii_store": str(root),
            "build_embeddings": True,
            "chunking_method": "paragraph",
        },
    )

    def no_processing(**kwargs):
        raise AssertionError("Embedding retry repeated file processing")

    monkeypatch.setattr(runs_routes, "run_worker", no_processing)
    client.bad = {"Temporarily rejected"}
    job = claim_next_queue_job("test")
    with pytest.raises(incremental.IncrementalEmbeddingError) as error:
        execute_job(job)
    complete_queue_job(job["id"], error=str(error.value))
    failed = get_run(run["id"])
    assert failed["status"] == "error" and failed["error_phase"] == "embedding"
    assert failed["indexing_progress"]["completed_documents"] == 1
    control_run(run["id"], "retry")
    client.calls.clear()
    client.bad.clear()
    execute_job(claim_next_queue_job("test"))
    assert client.calls == [["Temporarily rejected"]]
    restored = get_run(run["id"])
    assert restored["status"] == "done" and restored["indexing_status"] == "done"
    assert restored["completed"] == 2
    assert all(item["status"] == "done" for item in restored["items"])

    # Legacy workers reported file processing done even after indexing failed.
    restored.update(status="done", indexing_status="error")
    restored.pop("file_processing_status")
    save_run(restored)
    complete_queue_job(job["id"])
    control_run(run["id"], "retry")
    client.calls.clear()
    execute_job(claim_next_queue_job("test"))
    assert client.calls == []
    assert get_run(run["id"])["indexing_status"] == "done"


def test_legacy_vectors_survive_upgrade_without_embedding_unselected_documents(library):
    root, client = library
    old = document(root, "legacy.txt", "Legacy content")
    new = document(root, "new.txt", "Selected new content")
    import tomli_w

    directory = ensure_embeddings_dir(root)
    index = faiss.IndexFlatIP(3)
    original = np.array([[1.0, 0.0, 0.0]], dtype="float32")
    index.add(original)
    faiss.write_index(index, str(directory / "segments.faiss"))
    (directory / "segments.mapping.jsonl").write_text(
        json.dumps({"faiss_id": 0, "file_id": old, "source_relpath": "legacy.txt"})
        + "\n"
    )
    (directory / "segments.meta.toml").write_text(
        tomli_w.dumps(
            {
                "embeddings": {
                    "model": "test-model",
                    "provider": "openai-compatible",
                    "dimension": 3,
                    "count": 1,
                    "normalized": True,
                }
            }
        )
    )
    embed(root, [new])
    snapshot, rows, _ = published(root)
    assert client.calls == [["Selected new content"]]
    assert {r["file_id"] for r in rows} == {old, new}
    np.testing.assert_array_equal(
        faiss.read_index(str(snapshot / "segments.faiss")).reconstruct(0), original[0]
    )
    assert (directory / "segments.faiss").exists()


def test_full_rebuild_vectors_can_seed_incremental_updates_without_provider_calls(
    library, monkeypatch
):
    root, client = library
    first = document(root, "first.txt", "Fresh full rebuild")
    from osii.indexing import common

    monkeypatch.setattr(common, "create_embedding_client", lambda: client)
    common.embed_collection_resumable(
        root, model="test-model", chunking_method="paragraph"
    )
    client.calls.clear()
    report = embed(root, [first])
    assert client.calls == [] and report["reused_chunks"] == 1


def test_same_text_new_source_path_updates_mapping_without_embedding_again(library):
    root, client = library
    file_id = document(root, "same.txt", "Unchanged text")
    embed(root, [file_id])
    write_meta_toml(
        root,
        file_id,
        "new/location.txt",
        "location.txt",
        "text/plain",
        14,
        "2026-11-09T00:00:00Z",
        file_id[7:],
    )
    client.calls.clear()
    embed(root, [file_id])
    assert client.calls == []
    assert published(root)[1][0]["source_relpath"] == "new/location.txt"


def test_search_pins_one_snapshot_during_concurrent_publication(library, monkeypatch):
    root, client = library
    file_id = document(root, "same.txt", "Old text")
    embed(root, [file_id])
    old_snapshot, old_rows, _ = published(root)
    from osii.domain.artifacts.extraction_variants import primary_extraction_dir

    (primary_extraction_dir(root, file_id) / "text.txt").write_text("New text")
    embed(root, [file_id])
    new_snapshot = published(root)[0]
    namespace = ensure_embeddings_dir(root)
    incremental.publish_snapshot(namespace, old_snapshot)
    from osii.search import common

    original = common.load_faiss_index

    def switch_after_read(root, **kwargs):
        index = original(root, **kwargs)
        incremental.publish_snapshot(namespace, new_snapshot)
        return index

    monkeypatch.setattr(common, "load_faiss_index", switch_after_read)
    monkeypatch.setattr(
        common,
        "embed_query",
        lambda *args, **kwargs: np.asarray([[1, 0, 0]], dtype="float32"),
    )
    results = common.search_segments(root, "query", top_k=1)
    assert results[0]["embedding_key"] == old_rows[0]["embedding_key"]
    from osii.domain.catalog_db import _scan_indexes

    assert (
        len(_scan_indexes(root)) == 1
    )  # Old/orphan generations are not duplicate spaces.


def test_full_rebuild_keeps_old_index_until_retry_finishes(library):
    root, client = library
    old = document(root, "old", "Old published text")
    embed(root, [old])
    previous = published(root)[0]
    good = document(root, "new-good", "Healthy new text")
    bad = document(root, "new-bad", "Temporarily rejected text")
    client.bad = {"Temporarily rejected text"}
    client.calls.clear()
    with pytest.raises(incremental.IncrementalEmbeddingError):
        embed(root, [good, bad], rebuild_id="full-rebuild", batch_size=1)
    assert published(root)[0] == previous
    assert any("Healthy new text" in batch for batch in client.calls)
    client.bad.clear()
    client.calls.clear()
    result = embed(root, [good, bad], rebuild_id="full-rebuild", batch_size=1)
    assert result["completed_documents"] == 2
    assert client.calls == [["Temporarily rejected text"]]
    assert {row["file_id"] for row in published(root)[1]} == {good, bad}


def test_full_rebuild_can_replace_dimensions_and_pause_without_publication(library):
    root, client = library
    item = document(root, "document", "Document text")
    embed(root, [item])
    original = published(root)[0]
    client.dimension = 4
    paused = embed(root, [item], rebuild_id="new-dimension", should_stop=lambda: True)
    assert paused["paused"]
    assert published(root)[0] == original
    embed(root, [item], rebuild_id="new-dimension")
    assert len(next(iter(published(root)[2].values()))) == 4
    client.calls.clear()
    embed(root, [item])  # Imports rebuilt vectors, with no stale dimension cache.
    assert client.calls == []


def test_file_retry_adds_recovered_documents_to_embedding_membership(library, tmp_path, monkeypatch):
    root, client = library
    first = document(root, "first.txt", "Completed document")
    second = document(root, "second.txt", "Recovered document")
    embed(root, [first])
    from osii.api import runs_routes
    from osii.domain.processing.jobs import (
        create_run_record, save_run, enqueue_run, claim_next_queue_job,
        complete_queue_job, control_run, get_run,
    )
    from osii.worker import execute_job
    originals = tmp_path / "originals"
    originals.mkdir()
    paths = [originals / "first.txt", originals / "second.txt"]
    run = create_run_record(paths, originals, tmp_path / "uploads", osii_root=root)
    payload = {
        "osii_store": str(root), "resolved_files": [str(path) for path in paths],
        "queue_items": [], "include_subfolders": False, "include_patterns": [],
        "exclude_patterns": [], "context": "", "intake_name": "retry",
        "data_volume_root": str(tmp_path), "shared_root": str(originals),
        "upload_root": str(tmp_path / "uploads"), "parser_routes_path": str(tmp_path / "routes.yaml"),
        "build_embeddings": True, "chunking_method": "paragraph",
    }
    enqueue_run(run["id"], payload)
    job = claim_next_queue_job("initial-attempt")
    run = get_run(run["id"])
    run.update(status="done", workflow="intake", file_processing_status="done",
               indexing_status="done", indexing_file_ids=[first], operations={"embed": True})
    run["items"][0].update(status="done", file_id=first)
    run["items"][1].update(status="error", error="Temporary OCR failure")
    save_run(run)
    complete_queue_job(job["id"])
    def recover_file(**kwargs):
        current = get_run(kwargs["run_id"])
        assert current["items"][0]["status"] == "done"
        current["items"][1].update(status="done", error=None, file_id=second)
        current.update(status="done", completed=2)
        save_run(current)
    monkeypatch.setattr(runs_routes, "run_worker", recover_file)
    control_run(run["id"], "retry")
    client.calls.clear()
    execute_job(claim_next_queue_job("retry-after-restart"))
    restored = get_run(run["id"])
    assert restored["indexing_progress"]["total_documents"] == 2
    assert set(restored["indexing_file_ids"]) == {first, second}
    assert client.calls == [["Recovered document"]]
