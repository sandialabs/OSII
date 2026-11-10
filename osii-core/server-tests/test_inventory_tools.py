"""Hosted inventory and shared scope tools preserve source and permission boundaries."""

import threading
from pathlib import Path
from dataclasses import replace

import pytest
from sqlalchemy import update

from conftest import Provider, document, login
from osii.domain.processing.directory_scan import directory_batches
from osii.persistence.inventory import PostgresInventory
from osii.persistence.postgres import documents
from osii.server.inventory import execute_scan
from osii.server.library_tools import execute, snapshot
from osii.volume.models import ScanOptions, Filters, SelectionRequest


def inventory(app):
    return PostgresInventory(app.state.store, app.state.settings.source_root.resolve())


def complete_scan(app, inv, source, *, replay=False):
    store = app.state.store
    run = inv.start(source["id"], ScanOptions())
    job = store.claim("scanner")
    assert job["kind"] == "inventory_scan"
    scan, source = inv.scan_context(job, "scanner")
    while (path := inv.claim_directory(scan, job, "scanner")) is not None:
        for message in directory_batches(
            source, path, job["payload"], threading.Event(), batch_size=2
        ):
            if message[0] == "batch":
                inv.write_batch(scan, job, "scanner", message[1], message[2])
                if replay:
                    inv.write_batch(scan, job, "scanner", message[1], message[2])
            else:
                inv.finish_directory(scan, job, "scanner", path, message)
    failed, pending = inv.finish_scan(scan, job, "scanner")
    store.finish(job["id"], "scanner", [], failed, reschedule=pending and not failed)
    return inv.run(run["id"])


def test_scan_metadata_only_replay_filters_missing_and_selection(app, monkeypatch):
    root = app.state.settings.source_root
    (root / "nested").mkdir()
    (root / "a.txt").write_text("alpha")
    (root / "nested" / "b.pdf").write_text("beta")
    (root / ".hidden").write_text("hidden")
    (root / "link").symlink_to(root / "a.txt")
    inv = inventory(app)
    source = inv.register(str(root.resolve()))

    def forbidden(*args, **kwargs):
        raise AssertionError("Inventory read document contents")

    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    run = complete_scan(app, inv, source, replay=True)
    assert (
        run["status"] == "done" and run["failed"] == 0 and run["metadata_errors"] == 0
    )
    assert run["known_bytes"] == 9
    summary = inv.summary(Filters(source_id=source["id"]))
    assert summary["files"] == 2 and summary["bytes"] == 9 and summary["extracted"] == 0
    first = inv.entries(Filters(source_id=source["id"]), limit=1)
    assert first["next_cursor"] is not None
    assert (
        len(
            inv.entries(Filters(source_id=source["id"]), cursor=first["next_cursor"])[
                "items"
            ]
        )
        == 1
    )
    assert len(inv.entries(Filters(suffix="pdf"))["items"]) == 1
    frozen = inv.select(
        SelectionRequest(filters=Filters(source_id=source["id"]), max_files=2)
    )
    assert frozen["count"] == 2 and len(inv.verify_members(frozen["id"])) == 2
    sampled = [
        inv.select(
            SelectionRequest(
                filters=Filters(source_id=source["id"]), sample=True, seed="stable"
            )
        )
        for _ in range(2)
    ]
    assert [
        row["path"] for row in inv.selection_entries(sampled[0]["id"])["items"]
    ] == [row["path"] for row in inv.selection_entries(sampled[1]["id"])["items"]]
    (root / "a.txt").unlink()
    complete_scan(app, inv, source)
    assert inv.summary(Filters())["files"] == 1
    with pytest.raises(ValueError, match="stale"):
        inv.verify_members(frozen["id"])
    assert inv.selection_entries(frozen["id"])["items"][0]["size_bytes"] == 5


def test_pause_recovery_partial_and_fencing(app):
    root = app.state.settings.source_root
    (root / "first.txt").write_text("one")
    (root / "second.txt").write_text("two")
    inv = inventory(app)
    source = inv.register(str(root.resolve()))
    store = app.state.store
    run = inv.start(source["id"], ScanOptions())
    job = store.claim("old")
    scan, source = inv.scan_context(job, "old")
    assert inv.claim_directory(scan, job, "old") == ""
    message = next(
        directory_batches(source, "", job["payload"], threading.Event(), batch_size=1)
    )
    inv.write_batch(scan, job, "old", message[1], message[2])
    with pytest.raises(ValueError, match="incomplete"):
        inv.select(SelectionRequest(filters=Filters(source_id=source["id"])))
    assert (
        inv.select(
            SelectionRequest(
                filters=Filters(source_id=source["id"]), allow_partial=True
            )
        )["count"]
        == 1
    )
    inv.control(run["id"], "pause")
    failed, pending = inv.finish_scan(scan, job, "old")
    store.finish(job["id"], "old", [], failed, reschedule=pending)
    assert inv.run(run["id"])["status"] == "paused"
    with pytest.raises(ValueError):
        inv.write_batch(scan, job, "old", message[1], message[2])
    inv.control(run["id"], "resume")
    job = store.claim("new")
    failed, pending = execute_scan(
        store,
        replace(app.state.settings, source_root=root.resolve()),
        job,
        "new",
        threading.Event(),
        lambda _: None,
    )
    store.finish(job["id"], "new", [], failed, reschedule=pending)
    assert inv.run(run["id"])["status"] == "done"
    assert (
        inv.summary(Filters())["files"] == 2 and inv.run(run["id"])["known_bytes"] == 6
    )


def test_incomplete_directory_does_not_mark_old_entries_missing(app):
    root = app.state.settings.source_root
    (root / "old.txt").write_text("old")
    inv = inventory(app)
    source = inv.register(str(root.resolve()))
    complete_scan(app, inv, source)
    (root / "old.txt").unlink()
    run = inv.start(source["id"], ScanOptions())
    store = app.state.store
    job = store.claim("scanner")
    scan, _ = inv.scan_context(job, "scanner")
    inv.claim_directory(scan, job, "scanner")
    inv.finish_directory(
        scan, job, "scanner", "", ("error", "Disconnected mount", None)
    )
    failed, pending = inv.finish_scan(scan, job, "scanner")
    store.finish(job["id"], "scanner", [], failed)
    assert (
        inv.run(run["id"])["status"] == "error" and inv.summary(Filters())["files"] == 1
    )
    assert inv.summary(Filters())["scan_status"][0]["error"] == "Disconnected mount"


def test_api_admin_csrf_containment_and_frozen_intake(client, app):
    root = app.state.settings.source_root
    (root / "a.txt").write_text("first")
    inv = inventory(app)
    source = inv.register(str(root.resolve()))
    complete_scan(app, inv, source)
    assert client.get("/api/volume/sources").status_code == 401
    login(client, "reader")
    assert client.get("/api/volume/sources").status_code == 403
    login(client)
    assert (
        client.post("/api/volume/sources", json={"root": "../escape"}).status_code
        == 409
    )
    (root / "symlink").symlink_to(root.parent)
    assert (
        client.post(
            "/api/volume/sources", json={"root": str(root / "symlink")}
        ).status_code
        == 409
    )
    assert (
        client.get("/api/browse/page", params={"path": "../escape"}).status_code == 409
    )
    client.headers.pop("X-CSRF-Token")
    assert (
        client.post(f"/api/volume/sources/{source['id']}/scan", json={}).status_code
        == 403
    )
    login(client)
    selected = client.post(
        "/api/volume/selections", json={"filters": {"source_id": source["id"]}}
    )
    assert selected.status_code == 200, selected.text
    body = {"selection_id": selected.json()["id"], "operation": "missing"}
    preview = client.post("/api/admin/inventory/intake/preview", json=body)
    assert preview.status_code == 200, preview.text
    assert [row["path"] for row in preview.json()["items"]] == ["a.txt"]
    staged = client.post("/api/admin/inventory/intake/stage", json=body)
    assert staged.status_code == 200 and staged.json()["status"] == "staged"
    assert app.state.store.catalog_documents() == []
    (root / "a.txt").write_text("changed")
    assert (
        client.post("/api/admin/inventory/intake/stage", json=body).status_code == 409
    )


def test_cursor_owned_by_principal_and_mount_boundary(client, app):
    root = app.state.settings.source_root
    for i in range(4):
        (root / f"{i}.txt").write_text("test")
    # Production roots are resolved by Settings.environment.
    app.state.settings = replace(app.state.settings, source_root=root.resolve())
    login(client)
    result = client.get(
        "/api/browse/page", params={"limit": 1, "path": str(root.resolve())}
    )
    assert result.status_code == 200, result.text
    assert result.json()["parent_path"] is None
    token = result.json()["cursor"]
    assert token
    login(client, "curator")
    assert client.get("/api/browse/page", params={"cursor": token}).status_code == 403
    from osii.server.auth import password_hash

    admin = app.state.store.create_account(
        "second-admin", password_hash("second-administrator-password"), "admin"
    )
    app.state.store.change_account(admin, {"must_change_password": False})
    login(client, "second-admin", "second-administrator-password")
    assert client.get("/api/browse/page", params={"cursor": token}).status_code == 404
    login(client)
    assert client.delete("/api/browse/page/" + token).status_code == 200


def run_tool(app, jid):
    store = app.state.store
    job = store.claim("tool-worker")
    assert job["id"] == jid
    execute(
        store,
        app.state.settings,
        Provider(),
        job,
        "tool-worker",
        threading.Event(),
        lambda _: None,
    )
    store.finish(jid, "tool-worker", [])
    return store.job(jid)


@pytest.mark.parametrize("scope_kind", ["root", "folder", "collection"])
def test_scope_commit_rejects_inputs_changed_during_processor_call(client, app, monkeypatch, scope_kind):
    from osii.server import library_tools
    from osii.domain.storage.commits import CommitConflict
    store = app.state.store
    doc = document(store, app.state.settings.source_root, name="reports/report.txt")
    login(client)
    scope = {"scope_type": scope_kind}
    if scope_kind == "folder":
        scope["folder_id"] = "reports"
    elif scope_kind == "collection":
        scope["collection_id"] = client.post("/api/collections", json={
            "name": "Reports", "members": [doc["file_id"]], "visibility": "shared"}).json()["id"]
    queued = client.post("/api/enrichment-jobs/run", json={"enricher_name": "local.stats-keywords", "scope": scope})
    assert queued.status_code == 200, queued.text
    job = store.claim("scope-worker")
    invoke = library_tools.invoke
    def changed(*args, **kwargs):
        response = invoke(*args, **kwargs)
        with store.transaction() as conn:
            conn.execute(update(documents).where(documents.c.file_id == doc["file_id"]).values(text="Changed while processing"))
        return response
    monkeypatch.setattr(library_tools, "invoke", changed)
    with pytest.raises(CommitConflict, match="input text changed"):
        execute(store, app.state.settings, Provider(), job, "scope-worker", threading.Event(), lambda _: None)
    assert client.post("/api/products/list", json=scope).json()["products"] == []
    assert store.job(job["id"])["payload"]["items"][0]["status"] != "done"


def test_shared_library_tool_revision_candidates_and_permissions(
    client, app, monkeypatch
):
    root = app.state.settings.source_root
    doc = document(app.state.store, root)
    login(client)
    catalog = client.get("/api/enrichment-jobs/tools")
    assert catalog.status_code == 200, catalog.text
    assert catalog.json()["permissions"]["run"]
    body = {
        "enricher_name": "local.extractive-preview",
        "scope": {"scope_type": "root"},
    }
    result = client.post("/api/enrichment-jobs/run", json=body)
    assert result.status_code == 200, result.text
    jid = result.json()["run_id"]
    job = run_tool(app, jid)
    assert job["status"] == "done"
    assert job["payload"]["items"][0]["status"] == "done"
    product = client.post("/api/products/list", json=body["scope"]).json()["products"][
        0
    ]
    address = {"scope": body["scope"], "filename": product["filename"]}
    history = client.post("/api/products/revisions", json=address).json()
    assert (
        history["input_state"] == "current"
        and history["revisions"][0]["provenance"]["inputs"][0]["file_id"]
        == doc["file_id"]
    )
    edited = client.put(
        "/api/enrichments/revisions",
        json={
            **address,
            "expected_revision": history["current"],
            "markdown": "Human reviewed wiki",
        },
    )
    assert edited.status_code == 200, edited.text
    current = edited.json()["current"]
    assert (
        client.put(
            "/api/enrichments/revisions",
            json={
                **address,
                "expected_revision": history["current"],
                "markdown": "lost edit",
            },
        ).status_code
        == 409
    )
    second = client.post("/api/enrichment-jobs/run", json=body).json()["run_id"]
    run_tool(app, second)
    after = client.post("/api/products/revisions", json=address).json()
    assert after["current"] == current and len(after["revisions"]) == 3
    assert after["data"]["markdown"] == "Human reviewed wiki"
    generated = next(row for row in after["revisions"] if row["parent"] == current)
    assert generated["origin"] == "generated"
    login(client, "reader")
    assert (
        client.get("/api/enrichment-jobs/tools").json()["permissions"]["run"] is False
    )
    assert client.post("/api/enrichment-jobs/run", json=body).status_code == 403
    assert (
        client.put(
            "/api/products/revisions",
            json={**address, "expected_revision": current, "revision": generated["id"]},
        ).status_code
        == 403
    )
    assert (
        client.post("/api/products/revisions", json=address).json()["permissions"][
            "edit"
        ]
        is False
    )
    assert "frozen" not in client.get("/api/runs/" + jid).json()
    assert client.post("/api/runs/" + jid + "/retry").status_code == 403
    login(client, "curator")
    activated = client.put(
        "/api/products/revisions",
        json={**address, "expected_revision": current, "revision": generated["id"]},
    )
    assert activated.status_code == 200, activated.text
    assert (
        client.request(
            "DELETE",
            "/api/enrichments/payload",
            json={**address, "expected_revision": current},
        ).status_code
        == 409
    )


def test_frozen_scope_bounds_privacy_and_stale_results(client, app):
    store = app.state.store
    doc = document(store, app.state.settings.source_root, content="alpha " * 50000)
    admin = login(client)
    body = {"enricher_name": "local.stats-keywords", "scope": {"scope_type": "root"}}
    frozen = snapshot(store, body["scope"], admin["id"])
    assert frozen["text_chars"] < 180000 and frozen["truncated_documents"] == 1
    result = client.post("/api/enrichment-jobs/run", json=body)
    assert result.status_code == 200, result.text
    jid = result.json()["run_id"]
    assert run_tool(app, jid)["status"] == "done"
    products = client.post("/api/products/list", json=body["scope"]).json()["products"]
    assert products
    address = {"scope": body["scope"], "filename": products[0]["filename"]}
    with store.transaction() as c:
        c.execute(
            update(documents)
            .where(documents.c.file_id == doc["file_id"])
            .values(text="Changed primary text")
        )
    assert (
        client.post("/api/products/revisions", json=address).json()["input_state"]
        == "stale"
    )
    created = client.post(
        "/api/collections",
        json={
            "name": "Private inputs",
            "description": "",
            "members": [doc["file_id"]],
            "visibility": "private",
        },
    )
    assert created.status_code == 200, created.text
    collection = created.json()
    identity = collection.get("id") or collection["collection"]["id"]
    private = {
        "enricher_name": "local.stats-keywords",
        "scope": {"scope_type": "collection", "collection_id": identity},
    }
    queued = client.post("/api/enrichment-jobs/run", json=private)
    assert queued.status_code == 200, queued.text
    run_tool(app, queued.json()["run_id"])
    login(client, "reader")
    assert client.post("/api/products/list", json=private["scope"]).status_code == 422
    assert client.get("/api/runs/" + queued.json()["run_id"]).status_code == 422
    assert all(
        row["id"] != queued.json()["run_id"]
        for row in client.get("/api/runs").json()["runs"]
    )


def test_replaced_subtree_and_explicit_identity_rebind(app):
    root = app.state.settings.source_root
    (root / "nested").mkdir()
    (root / "nested" / "old.txt").write_text("old")
    inv = inventory(app)
    source = inv.register(str(root.resolve()))
    complete_scan(app, inv, source)
    frozen = inv.select(SelectionRequest(filters=Filters(source_id=source["id"])))
    (root / "nested" / "old.txt").unlink()
    (root / "nested").rmdir()
    (root / "nested").write_text("replacement")
    complete_scan(app, inv, source)
    assert [row["path"] for row in inv.entries(Filters())["items"]] == ["nested"]
    with app.state.store.transaction() as c:
        from osii.persistence.workspace_schema import inventory_sources

        c.execute(
            update(inventory_sources)
            .where(inventory_sources.c.id == source["id"])
            .values(inode="different-mount")
        )
    failed = complete_scan(app, inv, source)
    assert failed["status"] == "error" and failed["issue_code"] == "identity_changed"
    rebound = inv.rebind(source["id"], source["root"])
    assert rebound["generation"] == 2
    assert inv.summary(Filters())["files"] == 0
    with pytest.raises(ValueError, match="stale"):
        inv.frozen(frozen["id"])
    assert complete_scan(app, inv, rebound)["status"] == "done"


def test_tool_pause_commits_atomically_and_resume_reuses_saved_result(
    client, app, monkeypatch
):
    store = app.state.store
    document(store, app.state.settings.source_root)
    login(client)
    jid = client.post(
        "/api/enrichment-jobs/run",
        json={
            "enricher_name": "local.extractive-preview",
            "scope": {"scope_type": "root"},
        },
    ).json()["run_id"]
    from osii.server.processors import BUILTINS

    processor = BUILTINS["local.extractive-preview"]
    original = processor.synthesize
    calls = []

    def pausing(request):
        calls.append(1)
        store.control_job(jid, "pause", "")
        return original(request)

    monkeypatch.setattr(processor, "synthesize", pausing)
    job = store.claim("writer")
    execute(
        store,
        app.state.settings,
        Provider(),
        job,
        "writer",
        threading.Event(),
        lambda _: None,
    )
    assert (
        store.job(jid)["status"] == "paused"
        and store.job(jid)["payload"]["items"][0]["status"] == "done"
    )
    store.control_job(
        jid,
        "resume",
        lambda: __import__(
            "osii.server.intake", fromlist=["configuration_stamp"]
        ).configuration_stamp(store, app.state.settings),
    )
    assert run_tool(app, jid)["status"] == "done" and len(calls) == 1
    assert (
        len(
            client.post("/api/products/list", json={"scope_type": "root"}).json()[
                "products"
            ]
        )
        == 1
    )


def test_inventory_processed_handoff_links_current_revision(client, app):
    from test_intake_plans import execute as process

    store = app.state.store
    doc = document(store, app.state.settings.source_root)
    inv = inventory(app)
    source = inv.register(str(app.state.settings.source_root.resolve()))
    complete_scan(app, inv, source)
    frozen = inv.select(SelectionRequest(filters=Filters(source_id=source["id"])))
    login(client)
    staged = client.post(
        "/api/admin/inventory/intake/stage",
        json={
            "selection_id": frozen["id"],
            "operation": "process",
            "enricher_name": "local.stats-keywords",
        },
    )
    assert staged.status_code == 200, staged.text
    jid = staged.json()["id"]
    from osii.server.intake import configuration_stamp

    store.control_job(jid, "start", configuration_stamp(store, app.state.settings))
    result = process(app, jid)
    assert result["status"] == "done", result["logs"]
    assert inv.summary(Filters(text_state="extracted"))["files"] == 1
    assert inv.entries(Filters())["items"][0]["file_id"] == doc["file_id"]


def test_overview_and_tool_request_validation(client, app):
    document(app.state.store, app.state.settings.source_root)
    login(client)
    assert (
        client.post(
            "/api/scopes/overview", json={"scope": {"scope_type": "root"}}
        ).json()["processing"]["text_count"]
        == 1
    )
    assert (
        client.post(
            "/api/enrichment-jobs/run",
            json={
                "enricher_name": "local.stats-keywords",
                "scope": {"scope_type": "root"},
                "enricher_config": {"top_k": -1},
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/enrichment-jobs/run",
            json={
                "enricher_name": "local.stats-keywords",
                "scope": {"scope_type": "root"},
                "model_bindings": {"chat": "arbitrary"},
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/enrichment-jobs/run",
            json={
                "enricher_name": "local.stats-keywords",
                "scope": {"scope_type": "root"},
                "endpoint": "https://arbitrary.test",
            },
        ).status_code
        == 422
    )
    login(client, "reader")
    assert not client.post(
        "/api/scopes/overview", json={"scope": {"scope_type": "root"}}
    ).json()["permissions"]["run"]


def test_legacy_documents_keep_preferred_identity_for_tools_and_combined_embedding(
    client, app
):
    """Older hosted documents have extraction rows but no primary ID marker."""
    from test_intake_plans import execute as process
    from osii.server.intake import configuration_stamp

    store = app.state.store
    doc = document(store, app.state.settings.source_root)
    preferred = store.extraction_records(doc["file_id"])[0]["id"]
    legacy = {
        key: value
        for key, value in store.document(doc["file_id"])["metadata"].items()
        if key != "primary_extraction_id"
    }
    with store.transaction() as connection:
        connection.execute(
            update(documents)
            .where(documents.c.file_id == doc["file_id"])
            .values(metadata=legacy)
        )
    actor = login(client)
    frozen = snapshot(store, {"scope_type": "root"}, actor["id"])
    assert frozen["documents"][0]["extraction_id"] == preferred
    tool = client.post(
        "/api/enrichment-jobs/run",
        json={
            "enricher_name": "local.extractive-preview",
            "scope": {"scope_type": "root"},
        },
    )
    assert tool.status_code == 200, tool.text
    run_tool(app, tool.json()["run_id"])
    product = client.post("/api/products/list", json={"scope_type": "root"}).json()[
        "products"
    ][0]
    assert (
        client.post(
            "/api/products/revisions",
            json={"scope": {"scope_type": "root"}, "filename": product["filename"]},
        ).json()["input_state"]
        == "current"
    )
    store.save_configuration({"embedding_model": "synthetic-test-embedding"})
    staged = client.post(
        "/api/admin/intake/stage",
        json={
            "paths": [doc["source_relpath"]],
            "operation": "process",
            "embed": True,
            "enricher_name": "local.stats-keywords",
        },
    )
    assert staged.status_code == 200, staged.text
    jid = staged.json()["id"]
    store.control_job(jid, "start", configuration_stamp(store, app.state.settings))
    result = process(app, jid)
    assert result["status"] == "done", result["logs"]
    assert result["payload"]["items"][0]["steps"] == {
        "enrichment": "done",
        "embedding": "done",
    }
    assert (
        store.document(doc["file_id"])["metadata"]["embedding_provenance"][
            "input_revision"
        ]["representation_id"]
        == preferred
    )

    assert store.document(doc["file_id"])["text"] == doc["text"]
    assert [row["id"] for row in store.extraction_records(doc["file_id"])] == [preferred]
