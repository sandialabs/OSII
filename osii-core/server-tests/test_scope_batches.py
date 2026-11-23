import threading
from sqlalchemy import insert, select, update, func
from conftest import login, document, Provider
from osii.persistence.postgres import documents, jobs, now
from osii.persistence.workspace_schema import (
    scope_tool_batches as batches,
    scope_tool_sources as sources,
)
from osii.server import scope_batches
from osii.server.intake import configuration_stamp


def seed(store, count=1050):
    with store.transaction() as c:
        c.execute(
            insert(documents),
            [
                {
                    "file_id": f"file-{i:05}",
                    "sha256": f"hash-{i}",
                    "source_relpath": f"folder/report-{i}.txt",
                    "filename": f"report-{i}.txt",
                    "media_type": "text/plain",
                    "size_bytes": 24,
                    "text": f"Saved text document {i}.",
                    "metadata": {},
                    "active": True,
                    "updated_at": now(),
                }
                for i in range(count)
            ],
        )


def execute(app, jid):
    store = app.state.store
    job = store.claim("batch-worker")
    assert job["id"] == jid

    class TestProvider(Provider):
        def chat(self, model, messages, max_tokens=900, **kwargs):
            return super().chat(model, messages, max_tokens)

    logs = []
    try:
        pending = scope_batches.execute(
            store,
            app.state.settings,
            TestProvider(),
            job,
            "batch-worker",
            threading.Event(),
            logs.append,
        )
        store.finish(jid, "batch-worker", logs, reschedule=pending)
    except Exception:
        store.finish(jid, "batch-worker", logs, failed=True)
        raise
    return store.job(jid)


def submit(client, method="local.stats-keywords", scope=None):
    result = client.post(
        "/api/enrichment-jobs/run",
        json={"enricher_name": method, "scope": scope or {"scope_type": "root"}},
    )
    assert result.status_code == 200, result.text
    return result.json()["run_id"]


def test_whole_dataset_and_complete_long_text_are_frozen_and_processed(client, app):
    store = app.state.store
    seed(store)
    long_text = ("early words " * 20000) + " finalsentinel"
    with store.transaction() as c:
        c.execute(
            update(documents)
            .where(documents.c.file_id == "file-00000")
            .values(text=long_text)
        )
    login(client)
    jid = submit(client)
    assert "frozen" not in store.job(jid)["payload"]
    with store.engine.connect() as c:
        assert (
            c.execute(
                select(func.count()).select_from(sources).where(sources.c.job_id == jid)
            ).scalar()
            == 1050
        )
        rows = (
            c.execute(
                select(batches)
                .where(batches.c.job_id == jid)
                .order_by(batches.c.ordinal)
            )
            .mappings()
            .all()
        )
    original = [
        item["text"]
        for row in rows
        for item in row["inputs"]
        if item["file_id"] == "file-00000"
    ]
    assert "".join(original) == long_text
    assert all(
        sum(len(item["text"]) for item in row["inputs"]) <= 100000 for row in rows
    )
    run = execute(app, jid)
    assert run["status"] == "done", run["logs"]
    progress = run["payload"]["batch_progress"]
    assert progress["completed_documents"] == 1050
    assert progress["processed_characters"] == progress["text_characters"]
    assert progress["completed_batches"] == progress["map_batches"]
    detail = client.get(f"/api/enrichment-jobs/runs/{jid}/batches?limit=2").json()
    assert len(detail["items"]) == 2 and detail["next_cursor"] is not None
    assert all("result" not in row and "inputs" not in row for row in detail["items"])
    page = client.get(f"/api/enrichment-jobs/runs/{jid}/batches/map-0")
    assert page.status_code == 200, page.text
    assert page.json()["result"]["artifacts"]


def test_completed_batches_survive_pause_and_resume_without_duplicate_calls(
    client, app, monkeypatch
):
    seed(app.state.store, 80)
    login(client)
    jid = submit(client)
    store = app.state.store
    original = scope_batches.invoke
    calls = []

    def pausing(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(args[4].request_id)
        if len(calls) == 2:
            store.control_job(jid, "pause", "")
        return result

    monkeypatch.setattr(scope_batches, "invoke", pausing)
    assert execute(app, jid)["status"] == "paused"
    assert store.job(jid)["payload"]["batch_progress"]["completed_batches"] == 2
    store.control_job(jid, "resume", configuration_stamp(store, app.state.settings))
    assert execute(app, jid)["status"] == "done"
    assert len(calls) == 3


def test_batch_results_enforce_collection_visibility_and_source_changes(client, app):
    store = app.state.store
    doc = document(store, app.state.settings.source_root)
    login(client)
    collection = client.post(
        "/api/collections",
        json={
            "name": "Private",
            "members": [doc["file_id"]],
            "description": "",
            "visibility": "private",
        },
    ).json()
    scope = {"scope_type": "collection", "collection_id": collection["id"]}
    jid = submit(client, scope=scope)
    execute(app, jid)
    product = next(
        row
        for row in client.post("/api/products/list", json=scope).json()["products"]
        if row["artifact_type"] == "scope_batch_run"
    )
    address = {"scope": scope, "filename": product["filename"]}
    assert (
        client.post("/api/products/revisions", json=address).json()["input_state"]
        == "current"
    )
    with store.transaction() as c:
        c.execute(
            update(documents)
            .where(documents.c.file_id == doc["file_id"])
            .values(text="new text")
        )
    assert (
        client.post("/api/products/revisions", json=address).json()["input_state"]
        == "stale"
    )
    login(client, "reader")
    assert client.get(f"/api/enrichment-jobs/runs/{jid}/batches").status_code in (
        403,
        404,
        422,
    )
    assert client.get(f"/api/enrichment-jobs/runs/{jid}/batches/map-0").status_code in (
        403,
        404,
        422,
    )


def test_model_synthesis_reduces_all_batches_and_keeps_intermediate_results(
    client, app
):
    store = app.state.store
    seed(store, 70)
    store.save_configuration({"chat_model": "test-chat"})
    login(client)
    jid = submit(client, "openai.synthesizer")
    run = execute(app, jid)
    assert run["status"] == "done", run["logs"]
    assert run["payload"]["batch_progress"]["reduce_batches"] > 0
    products = client.post("/api/products/list", json={"scope_type": "root"}).json()[
        "products"
    ]
    assert {row["artifact_type"] for row in products} == {
        "scope_batch_run",
        "wiki_markdown",
    }
    with store.engine.connect() as c:
        assert (
            c.execute(
                select(func.count()).where(
                    batches.c.job_id == jid, batches.c.result.is_(None)
                )
            ).scalar()
            == 0
        )
