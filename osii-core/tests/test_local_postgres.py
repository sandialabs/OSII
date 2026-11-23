"""Standalone Workbench integration against an isolated real PostgreSQL schema."""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import uuid

import pytest

from osii.domain.storage.backend import BackendSettings, LibraryBackend


@pytest.fixture
def local_pg(request):
    url = os.environ.get("OSII_READ_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set OSII_READ_TEST_DATABASE_URL for real PostgreSQL tests")
    from sqlalchemy import create_engine, text
    from osii.domain.storage.postgres_schema import initialize

    admin = create_engine(url.replace("postgresql://", "postgresql+psycopg://", 1))
    schema = "local_workbench_" + uuid.uuid4().hex
    with admin.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    # Include the schema in the URL so the same configuration reaches app/worker.
    configured = admin.url.update_query_dict(
        {"options": f"-csearch_path={schema}"}
    ).render_as_string(hide_password=False)
    engine = create_engine(configured)
    try:
        if getattr(request, "param", True):
            initialize(engine)
        yield configured, engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


def test_backend_settings_default_is_sidecar_and_ignores_ambient_url():
    settings = BackendSettings.from_environment({"DATABASE_URL": "secret"})
    assert settings.kind == "sidecar" and settings.database_url == ""
    for env in (
        {"OSII_STORAGE_BACKEND": "oops"},
        {"OSII_STORAGE_BACKEND": "postgres"},
        {"OSII_STORAGE_BACKEND": "postgres", "DATABASE_URL": "sqlite:///data"},
    ):
        with pytest.raises(ValueError):
            BackendSettings.from_environment(env)
    assert "password" not in repr(
        BackendSettings("postgres", "postgresql://name:password@localhost/db")
    )


def test_explicit_schema_is_account_free_and_cannot_overwrite(local_pg):
    from sqlalchemy import text
    from osii.domain.storage.postgres_schema import initialize, validate

    _, engine = local_pg
    validate(engine)
    with engine.connect() as conn:
        names = set(
            conn.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname=current_schema()"
                )
            ).scalars()
        )
    assert not names & {"users", "sessions", "identities", "audit"}
    with pytest.raises(ValueError, match="empty"):
        initialize(engine)
    validate(engine)


def seed(root):
    from test_library_reads import seed_sidecars

    seed_sidecars(root)
    (root / "objects/sha256-a/edited_text.json").write_text(
        json.dumps(
            {
                "segments": [
                    {"id": "seg-000001", "text": "Human corrected neutron calibration."}
                ]
            }
        )
    )
    (root / "expert-context.md").write_text("Subject matter guidance")
    (root / "state").mkdir()
    (root / "state/secrets.env").write_text("NEVER_IMPORT=this-secret")
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_one_way_import_preserves_text_artifacts_collections_and_source(
    local_pg, tmp_path
):
    from sqlalchemy import text
    from osii.domain.storage.sidecar_import import plan_import, apply_import
    from osii.domain.read.postgres import PostgresLibraryReader

    _, engine = local_pg
    root = tmp_path / ".osii"
    before = seed(root)
    plan = plan_import(root)
    assert not plan.summary()["changes_source"]
    report = apply_import(engine, plan)
    assert report["documents"] == 3 and report["collections"] == 1
    reader = PostgresLibraryReader(engine)
    assert (
        reader.get_representation("sha256-a").text
        == "Human corrected neutron calibration."
    )
    assert reader.get_representation("sha256-a").kind == "edited_text"
    from test_library_reads import TEXT

    assert reader.get_representation("sha256-a", "canonical").text == TEXT
    from osii.domain.read.contracts import ReadScope

    assert [
        d.file_id
        for d in reader.list_documents(ReadScope("collection", "col-test")).items
    ] == ["sha256-b"]
    with engine.connect() as conn:
        paths = conn.execute(text("SELECT path FROM import_files")).scalars().all()
    assert not any("secrets" in p for p in paths)
    assert before == {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    with pytest.raises(ValueError, match="empty"):
        apply_import(engine, plan)
    assert reader.list_documents().total == 3


def test_import_changed_source_rolls_back_and_preview_needs_no_database(
    local_pg, tmp_path, capsys, monkeypatch
):
    from osii.domain.storage.sidecar_import import plan_import, apply_import
    from osii.storage_cli import main
    from sqlalchemy import text

    root = tmp_path / ".osii"
    seed(root)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert main(["import-sidecars", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["imported"] is False
    plan = plan_import(root)
    (root / "objects/sha256-b/text.txt").write_text("Changed during import")
    with pytest.raises(ValueError, match="changed"):
        apply_import(local_pg[1], plan)
    with local_pg[1].connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM documents")).scalar() == 0


@pytest.fixture
def pg_client(local_pg, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import osii.main as main

    original_module = dict(main.__dict__)

    runtime = tmp_path / "runtime"
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setenv("OSII_STORAGE_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", local_pg[0])
    monkeypatch.setenv("OSII_ROOT", str(runtime))
    monkeypatch.setenv("SHARED_VOLUME_ROOT", str(source))
    monkeypatch.setenv("UPLOAD_ORIGINALS_ROOT", str(tmp_path / "uploads"))
    monkeypatch.setenv("OSII_CONFIG_DIR", str(tmp_path / "deployment"))
    monkeypatch.setenv("CHAT_PROVIDER_CHAIN", "extractive")
    try:
        main = importlib.reload(main)
        with TestClient(main.app) as client:
            yield client, main.app, source, runtime
    finally:
        # Other suites retain the original app object. Restore its composition
        # globals too, rather than leaving its mounted inventory uninitialized.
        main.__dict__.update(original_module)


def test_empty_workbench_has_no_auth_no_catalog_or_silent_import(pg_client):
    client, app, source, runtime = pg_client
    assert client.get("/api/runtime").json()["storage_backend"] == "postgres"
    assert client.get("/api/runtime").json()["user_authentication"] is False
    assert client.get("/api/catalog/files").json()["total"] == 0
    assert client.get("/api/workbench/home").json()["documents"] == 0
    assert client.get("/api/auth/me").status_code == 404
    assert not (runtime / "state/catalog.sqlite3").exists()
    assert not (runtime / "state/jobs.sqlite3").exists()
    assert client.post("/api/catalog/rebuild").status_code == 409


def test_postgres_research_and_source_rescan_use_saved_library(pg_client, monkeypatch):
    file_id, _ = intake(pg_client, monkeypatch)
    client, app, source, runtime = pg_client
    scope = {"scope_type": "object", "file_id": file_id}
    report = client.post(
        "/api/research/report",
        json={"scope": scope, "prompt": "Describe the detector calibration"},
    )
    assert report.status_code == 200, report.text
    assert (
        report.json()["provider"] == "extractive"
        and report.json()["sources"][0]["file_id"] == file_id
    )
    (source / "one.txt").rename(source / "moved.txt")
    preview = client.post("/api/intake/rescan-sources", json={})
    assert preview.status_code == 200 and preview.json()["summary"]["moved"] == 1
    applied = client.post("/api/intake/rescan-sources", json={"apply": True})
    assert applied.status_code == 200, applied.text
    assert (
        app.state.postgres_library.reader.get_document(file_id).filename == "moved.txt"
    )
    assert client.get(f"/api/objects/{file_id}/source").status_code == 200
    assert not (runtime / "objects").exists()


def test_postgres_rag_profiles_reuse_grounded_text_and_reject_unavailable_methods(
    pg_client, monkeypatch
):
    pytest.importorskip("haystack")
    file_id, _ = intake(pg_client, monkeypatch)
    client, _, _, runtime = pg_client
    payload = {
        "query": "detector calibration",
        "scope": {"scope_type": "object", "file_id": file_id},
    }
    compared = client.post(
        "/api/chat/compare",
        json={**payload, "profile_ids": ["lexical-v1", "hybrid-v1"]},
    )
    assert compared.status_code == 200, compared.text
    for run in compared.json()["runs"]:
        response = run["response"]
        assert (
            response["provider"] == "extractive"
            and response["citations"][0]["file_id"] == file_id
        )
        assert response["experiment"]["consistency"] == "postgres-revision-guard"
    for profile in ("not-a-profile", "iterative-v1", "hybrid-reranked-v1"):
        assert (
            client.post(
                "/api/chat", json={**payload, "profile_id": profile}
            ).status_code
            == 422
        )
    assert not (runtime / "embeddings/chunks/chunks.jsonl").exists()


def fake_processor(root, name, kind):
    from osii.processor_sdk import (
        ProcessorDescriptor,
        Capability,
        ExtractionResponse,
        TextSegment,
        SynthesisResponse,
        EnrichmentResponse,
        Artifact,
        TableArtifactData,
        TableColumn,
        EmbeddingResponse,
        EmbeddingVector,
    )

    descriptor = ProcessorDescriptor(
        name=name,
        version="1",
        display_name=name,
        description="test",
        kind=kind,
        capabilities=Capability(
            scope_types=["object", "folder", "collection", "root"],
            output_kinds=["table"],
        ),
    )

    class Client:
        def extract(self, request):
            return ExtractionResponse(
                request_id=request.request_id,
                processor=descriptor,
                segments=[
                    TextSegment(
                        id="seg-000001",
                        text=__import__("base64")
                        .b64decode(request.document.content_base64)
                        .decode(),
                        source_origin={"page": 1, "bbox": [0, 0, 1, 1]},
                    )
                ],
            )

        def synthesize(self, request):
            return SynthesisResponse(
                request_id=request.request_id,
                processor=descriptor,
                markdown="# A grounded summary",
            )

        def enrich(self, request):
            return EnrichmentResponse(
                request_id=request.request_id,
                processor=descriptor,
                artifacts=[
                    Artifact(
                        id="statistics",
                        kind="table",
                        media_type="application/json",
                        standard_data=TableArtifactData(
                            title="Statistics",
                            columns=[
                                TableColumn(
                                    key="count", label="Count", data_type="integer"
                                )
                            ],
                            rows=[{"count": len(request.scope.documents)}],
                        ),
                    )
                ],
            )

        def embed(self, request):
            return EmbeddingResponse(
                request_id=request.request_id,
                processor=descriptor,
                model=request.config["model"],
                normalized=True,
                vectors=[
                    EmbeddingVector(id=row.id, vector=[1.0, 0.0], dimensions=2)
                    for row in request.inputs
                ],
            )

    return descriptor, Client()


def drain(flow, limit=60):
    for _ in range(limit):
        claim = flow.queue.claim("test-worker")
        if claim is None:
            return
        flow.step(claim.lease)
    raise AssertionError("Queue did not drain")


def test_full_workbench_intake_browse_edit_collections_jobs_and_products(
    pg_client, monkeypatch
):
    from osii.domain.processing import postgres_workflow

    monkeypatch.setattr(postgres_workflow, "processor", fake_processor)
    client, app, source, runtime = pg_client
    (source / "one.txt").write_text(
        "Neutron detector calibration.\nResults are reproducible."
    )
    (source / "two.txt").write_text("Detector experiment data and calibration results.")
    response = client.post(
        "/api/runs",
        json={
            "queue_paths": [str(source)],
            "run_extraction": True,
            "extract_mode": "missing",
            "build_embeddings": False,
        },
    )
    assert response.status_code == 200, response.text
    run_id = response.json()["id"]
    flow = app.state.postgres_workflow
    claim = flow.queue.claim("test-worker")
    flow.step(claim.lease)
    assert client.get("/api/catalog/files").json()["total"] == 1
    drain(flow)
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "done"
    files = client.get("/api/catalog/files").json()["items"]
    assert len(files) == 2
    file_id = files[0]["file_id"]
    assert client.get(f"/api/objects/{file_id}").json()["overview"]["text_count"] == 1
    assert client.get(f"/api/objects/{file_id}/source").status_code == 200
    assert (
        client.get(f"/api/objects/{file_id}/manifest").json()["records"][0][
            "source_origin"
        ]["page"]
        == 1
    )
    original = client.get(f"/api/objects/{file_id}/texts/preferred").json()["text"]
    edit = client.put(
        f"/api/objects/{file_id}/texts/edited",
        json={
            "segments": [{"id": "seg-000001", "text": "Human corrected calibration"}],
            "expected_revision": None,
        },
    )
    assert edit.status_code == 200, edit.text
    assert (
        client.get(f"/api/objects/{file_id}/texts/preferred").json()["text"]
        == "Human corrected calibration"
    )
    canonical = client.get(f"/api/objects/{file_id}/extractions/canonical/texts").json()
    assert canonical["text"] == original
    assert (
        client.put(
            f"/api/objects/{file_id}/texts/edited",
            json={"segments": [], "expected_revision": None},
        ).status_code
        == 409
    )
    collection = client.post("/api/collections", json={"name": "Calibration"}).json()[
        "collection"
    ]
    cid = collection["id"]
    assert collection["created_utc"]
    assert (
        client.patch(f"/api/collections/{cid}", json={"color": "#123456"}).json()[
            "collection"
        ]["color"]
        == "#123456"
    )
    assert (
        client.get(f"/api/collections/{cid}").json()["artifact_summary"]["artifacts"][
            "member_count"
        ]
        == 0
    )
    assert (
        client.post(
            f"/api/collections/{cid}/members", json={"file_ids": [file_id]}
        ).status_code
        == 200
    )
    assert client.post(
        "/api/scopes/describe", json={"scope_type": "collection", "collection_id": cid}
    ).json()["member_file_ids"] == [file_id]
    job = client.post(
        "/api/enrichment-jobs/run",
        json={
            "scope": {"scope_type": "collection", "collection_id": cid},
            "enricher_name": "test.stats",
        },
    )
    assert job.status_code == 200, job.text
    drain(flow)
    products = client.post(
        "/api/products/list", json={"scope_type": "collection", "collection_id": cid}
    ).json()["products"]
    standard = next(p for p in products if p["artifact_type"] == "table")
    payload = {
        "scope": {"scope_type": "collection", "collection_id": cid},
        "filename": standard["filename"],
    }
    history = client.post("/api/products/revisions", json=payload).json()
    data = {**history["data"], "title": "Curated statistics"}
    saved = client.put(
        "/api/products/revisions",
        json={**payload, "data": data, "expected_revision": history["current"]},
    )
    assert saved.status_code == 200, saved.text
    assert len(saved.json()["revisions"]) == 2
    assert not (runtime / "objects").exists()
    assert not (runtime / "collections").exists()
    assert not (runtime / "state/jobs.sqlite3").exists()


def test_queue_pause_cancel_retry_never_starts_another_claim(pg_client, monkeypatch):
    from osii.domain.processing import postgres_workflow

    monkeypatch.setattr(postgres_workflow, "processor", fake_processor)
    client, app, source, _ = pg_client
    (source / "one.txt").write_text("Neutron calibration")
    response = client.post("/api/runs", json={"queue_paths": [str(source)]})
    jid = response.json()["id"]
    assert client.post(f"/api/runs/{jid}/pause").json()["status"] == "paused"
    assert app.state.postgres_workflow.queue.claim("test") is None
    assert client.post(f"/api/runs/{jid}/resume").json()["status"] == "queued"
    assert client.post(f"/api/runs/{jid}/cancel").json()["status"] == "cancelled"
    assert app.state.postgres_workflow.queue.claim("test") is None


def intake(pg_client, monkeypatch, **options):
    from osii.domain.processing import postgres_workflow

    monkeypatch.setattr(postgres_workflow, "processor", fake_processor)
    client, app, source, _ = pg_client
    (source / "one.txt").write_text(
        "Neutron detector calibration and reproducible experimental results."
    )
    response = client.post("/api/runs", json={"queue_paths": [str(source)], **options})
    assert response.status_code == 200, response.text
    drain(app.state.postgres_workflow)
    return client.get("/api/catalog/files").json()["items"][0][
        "file_id"
    ], response.json()["id"]


def test_combined_intake_products_vectors_and_search(pg_client, monkeypatch):
    file_id, job_id = intake(
        pg_client,
        monkeypatch,
        synthesizer_name="test.preview",
        enricher_name="test.stats",
        build_embeddings=True,
        embedder_name="test.embedder",
        embedding_model="test-model",
    )
    client, app, _, runtime = pg_client
    run = client.get(f"/api/runs/{job_id}").json()
    assert run["status"] == "done", run
    assert run["items"][0]["steps"] == {
        "extraction": "done",
        "synthesizer": "done",
        "enricher": "done",
        "embedding": "done",
    }
    assert "tasks" not in run and "embedding_checkpoint" not in json.dumps(run)
    assert (
        client.get(f"/api/objects/{file_id}/syntheses").json()["current_text"]
        == "# A grounded summary"
    )
    scope = {"scope_type": "object", "file_id": file_id}
    products = client.post("/api/products/list", json=scope).json()["products"]
    assert any(p["artifact_type"] == "table" for p in products)
    reader = app.state.library_backend.reader
    assert any(p.kind == "table" for p in reader.list_artifacts(file_id).items)
    rows = app.state.postgres_library.query("SELECT * FROM chunks")
    assert rows and all(row["embedding"] == [1.0, 0.0] for row in rows)
    result = client.post(
        "/api/search", json={"query": "calibration", "mode": "lexical", "scope": scope}
    )
    assert result.status_code == 200, result.text
    assert result.json()["results"]
    hybrid = client.post(
        "/api/search", json={"query": "calibration", "mode": "hybrid", "scope": scope}
    )
    assert hybrid.status_code == 200, hybrid.text
    assert (
        client.post(
            "/api/search",
            json={"query": "calibration", "mode": "semantic", "scope": scope},
        ).status_code
        == 422
    )
    assert not (runtime / "objects").exists()


def test_pause_cancel_combined_run_keeps_browsable_files_without_detached_ai_jobs(
    pg_client, monkeypatch
):
    from osii.domain.processing import postgres_workflow

    monkeypatch.setattr(postgres_workflow, "processor", fake_processor)
    client, app, source, _ = pg_client
    (source / "one.txt").write_text("Neutron calibration")
    job = client.post(
        "/api/runs",
        json={
            "queue_paths": [str(source)],
            "synthesizer_name": "test.preview",
            "enricher_name": "test.stats",
        },
    ).json()
    flow = app.state.postgres_workflow
    claim = flow.queue.claim("test")
    flow.step(claim.lease)
    assert client.get("/api/catalog/files").json()["total"] == 1
    assert len(flow.queue.get(job["id"]).payload["tasks"]) == 2
    assert client.post(f"/api/runs/{job['id']}/pause").status_code == 200
    assert flow.queue.claim("test") is None
    assert client.post(f"/api/runs/{job['id']}/cancel").status_code == 200
    assert flow.queue.claim("test") is None
    assert len(flow.queue.list()) == 1
    assert (
        app.state.postgres_library.query("SELECT count(*) AS n FROM scope_products")[0][
            "n"
        ]
        == 0
    )


def test_text_edit_revision_clear_history_and_lexical_refresh(pg_client, monkeypatch):
    file_id, _ = intake(
        pg_client,
        monkeypatch,
        build_embeddings=True,
        embedder_name="test.embedder",
        embedding_model="test-model",
    )
    client, app, _, _ = pg_client
    original = app.state.library_backend.reader.get_representation(
        file_id, "canonical"
    ).text
    editor = app.state.library_backend.text
    saved = editor.save(
        file_id,
        [{"id": "seg-000001", "text": "Zirconium human correction"}],
        expected_revision=None,
    )
    with pytest.raises(Exception, match="changed"):
        editor.save(file_id, [], expected_revision=None)
    assert not any(
        row["embedding"]
        for row in app.state.postgres_library.query("SELECT embedding FROM chunks")
    )
    result = client.post("/api/search", json={"query": "zirconium", "mode": "lexical"})
    assert result.status_code == 200, result.text
    assert result.json()["results"]
    editor.save(file_id, None, expected_revision=saved.revision)
    assert app.state.library_backend.reader.get_representation(file_id).text == original
    history = app.state.postgres_library.query(
        "SELECT metadata->'edited_text_history' AS history FROM documents"
    )[0]["history"]
    assert (
        len(history) == 2
        and history[0]["text"] == "Zirconium human correction"
        and history[1]["text"] is None
    )
    meta = client.get(f"/api/objects/{file_id}").json()["meta"]
    assert "edited_text_history" not in meta
    assert (
        client.post("/api/scopes/overview", json={"scope_type": "root"}).json()[
            "dates"
        ]["modified"]["recorded_count"]
        == 1
    )


def test_embedding_retry_resumes_batches_and_hides_checkpoint(pg_client, monkeypatch):
    from osii.domain.processing import postgres_workflow

    client, app, source, _ = pg_client
    (source / "long.txt").write_text(
        " ".join(f"Detector calibration experiment {n}." for n in range(300))
    )
    calls = []
    fail = [True]

    def processors(root, name, kind):
        descriptor, inner = fake_processor(root, name, kind)
        if kind == "embedder":
            embed = inner.embed

            def embedding(request):
                calls.append(request.request_id)
                if len(calls) == 2 and fail[0]:
                    raise ValueError("Temporary embedding outage")
                return embed(request)

            inner.embed = embedding
        return descriptor, inner

    monkeypatch.setattr(postgres_workflow, "processor", processors)
    job = client.post(
        "/api/runs",
        json={
            "queue_paths": [str(source)],
            "build_embeddings": True,
            "embedder_name": "test.embedder",
            "embedding_model": "test-model",
            "chunking_method": "window",
            "chunk_size": 64,
            "chunk_overlap": 8,
        },
    ).json()
    flow = app.state.postgres_workflow
    claim = flow.queue.claim("test")
    flow.step(claim.lease)
    claim = flow.queue.claim("test")
    with pytest.raises(ValueError, match="outage"):
        flow.step(claim.lease)
    flow.queue.finish(claim.lease, error="Temporary embedding outage")
    assert flow.queue.get(job["id"]).payload["items"][0]["embedding_checkpoint"][
        "batches"
    ]
    assert "embedding_checkpoint" not in json.dumps(
        client.get(f"/api/runs/{job['id']}").json()
    )
    fail[0] = False
    assert client.post(f"/api/runs/{job['id']}/retry").status_code == 200
    drain(flow)
    assert flow.queue.get(job["id"]).state == "done"
    assert calls.count(calls[0]) == 1
    assert all(
        row["embedding"]
        for row in app.state.postgres_library.query("SELECT embedding FROM chunks")
    )


@pytest.mark.parametrize("kind", ["sidecar", "postgres"])
def test_text_authoring_shared_port_parity(local_pg, tmp_path, kind):
    from osii.domain.storage.sidecar_import import plan_import, apply_import

    root = tmp_path / ".osii"
    seed(root)
    settings = BackendSettings(kind, local_pg[0] if kind == "postgres" else "")
    if kind == "postgres":
        apply_import(local_pg[1], plan_import(root))
    backend = LibraryBackend(root, settings)
    try:
        current = backend.text.get("sha256-a")
        changed = backend.text.save(
            "sha256-a",
            [{"id": "seg-000001", "text": "Updated by a human"}],
            expected_revision=current.revision,
        )
        assert (
            changed.text == "Updated by a human"
            and changed.revision != current.revision
        )
        assert (
            backend.reader.get_representation("sha256-a", "canonical").text
            != changed.text
        )
        with pytest.raises(Exception, match="changed"):
            backend.text.save("sha256-a", [], expected_revision=current.revision)
    finally:
        backend.close()


def test_postgres_collection_package_roundtrip_preserves_edits_labels_and_products(
    pg_client, local_pg, monkeypatch
):
    from osii.domain.storage.postgres_packages import (
        export_collection,
        import_collection,
    )

    file_id, _ = intake(pg_client, monkeypatch, enricher_name="test.stats")
    client, app, source, runtime = pg_client
    lib = app.state.postgres_library
    collection = lib.backend.collections.create("Demo")
    lib.backend.collections.replace_members(
        collection.collection_id, [file_id], expected_version=collection.version
    )
    edit = lib.backend.text.save(
        file_id,
        [{"id": "seg-000001", "text": "Human curated calibration"}],
        expected_revision=None,
    )
    lib.set_setting(
        "governance:" + file_id,
        {
            "tags": ["review"],
            "sensitivity_labels": ["internal"],
            "handling_notes": "Keep label",
        },
    )
    before = (source / "one.txt").read_bytes()
    image = b"\x89PNG\r\n\x1a\nexample-region"
    import base64

    with lib.engine.begin() as conn:
        lib.sql(
            conn,
            "INSERT INTO artifacts VALUES('region',:file,'image',CAST(:payload AS jsonb))",
            file=file_id,
            payload=json.dumps(
                {
                    "id": "region",
                    "kind": "image",
                    "media_type": "image/png",
                    "data_base64": base64.b64encode(image).decode(),
                    "source_origin": {"page": 2, "bbox": [0.1, 0.2, 0.5, 0.6]},
                }
            ),
        )
    content = export_collection(lib, collection.collection_id)
    import zipfile
    from io import BytesIO

    with zipfile.ZipFile(BytesIO(content)) as archive:
        assert not any("secrets" in p or "inventory" in p for p in archive.namelist())
    # Clear only the isolated test schema, then explicitly import the package.
    with local_pg[1].begin() as conn:
        lib.sql(
            conn,
            "TRUNCATE documents,extractions,chunks,artifacts,collections,scope_products,scope_revisions,settings,import_files,jobs CASCADE",
        )
    result = import_collection(lib, content)
    assert result["ok"] and result["indexes_rebuild_required"]
    assert lib.backend.reader.get_representation(file_id).text == edit.text
    assert lib.setting("governance:" + file_id)["sensitivity_labels"] == ["internal"]
    assert lib.backend.collections.get(collection.collection_id).member_ids == (
        file_id,
    )
    assert lib.enrichments({"scope_type": "object", "file_id": file_id})
    images = lib.images(file_id)
    assert images and images[0]["source_origin"]["page"] == 2
    assert lib.reader.get_artifact(file_id, images[0]["id"]).data == image
    assert import_collection(lib, content)["ok"]
    assert (source / "one.txt").read_bytes() == before
    assert not (runtime / "objects").exists()


def test_deletion_previews_block_active_work_and_leave_originals_by_default(
    pg_client, monkeypatch
):
    file_id, _ = intake(pg_client, monkeypatch, enricher_name="test.stats")
    client, app, source, _ = pg_client
    path = f"/api/objects/{file_id}"
    preview = client.post(path + "/deletion-preview", json={"mode": "sidecar_only"})
    assert preview.status_code == 200, preview.text
    data = preview.json()
    assert data["storage_backend"] == "postgres" and data["source_will_remain"]
    response = client.request(
        "DELETE",
        path,
        json={
            "mode": "sidecar_only",
            "preview_token": data["preview_token"],
            "confirmation": file_id,
        },
    )
    assert response.status_code == 200, response.text
    assert (source / "one.txt").exists()
    assert client.get("/api/catalog/files").json()["total"] == 0


def test_imported_document_deletion_retains_other_documents_and_attachments(
    local_pg, tmp_path
):
    from osii.domain.storage.sidecar_import import plan_import, apply_import
    from osii.domain.storage.postgres_library import PostgresLibrary

    root = tmp_path / ".osii"
    seed(root)
    attachment = root / "objects/sha256-b/artifacts/keep.bin"
    attachment.parent.mkdir()
    attachment.write_bytes(b"Other document's attachment")
    apply_import(local_pg[1], plan_import(root))
    backend = LibraryBackend(
        tmp_path / "runtime", BackendSettings("postgres", local_pg[0])
    )
    try:
        lib = PostgresLibrary(backend)
        preview = lib.deletion_preview("sha256-a", "sidecar_only")
        lib.delete_document(
            "sha256-a", "sidecar_only", preview["preview_token"], "sha256-a"
        )
        assert lib.reader.get_document("sha256-a") is None
        assert lib.reader.get_document("sha256-b") is not None
        assert (
            lib.query(
                "SELECT content FROM import_files WHERE path='objects/sha256-b/artifacts/keep.bin'"
            )[0]["content"]
            == attachment.read_bytes()
        )
        assert not lib.query(
            "SELECT path FROM import_files WHERE left(path,17)='objects/sha256-a/'"
        )
        assert (
            root / "objects/sha256-a/text.txt"
        ).exists()  # Original sidecar backup untouched.
    finally:
        backend.close()


def test_deletion_rejects_stale_preview_and_active_jobs(pg_client, monkeypatch):
    file_id, _ = intake(pg_client, monkeypatch)
    client, app, _, _ = pg_client
    lib = app.state.postgres_library
    preview = lib.deletion_preview(file_id, "sidecar_only")
    pending = app.state.postgres_workflow.queue.submit(
        "local-scope", {"file_id": file_id, "items": []}
    )
    from osii.domain.storage.authoring import AuthoringConflict

    with pytest.raises(AuthoringConflict, match="changed"):
        lib.delete_document(file_id, "sidecar_only", preview["preview_token"], file_id)
    current = lib.deletion_preview(file_id, "sidecar_only")
    assert current["active_jobs"]
    with pytest.raises(AuthoringConflict, match="Cancel"):
        lib.delete_document(file_id, "sidecar_only", current["preview_token"], file_id)
    app.state.postgres_workflow.queue.control(pending.job_id, "cancel")
    assert lib.reader.get_document(file_id) is not None


def test_inventory_selection_uses_database_status_without_replacing_sqlite(
    pg_client, monkeypatch
):
    import threading
    from osii.volume.models import Filters, ScanOptions, SelectionRequest
    from osii.volume.worker import execute
    from osii.domain.processing import postgres_workflow

    monkeypatch.setattr(postgres_workflow, "processor", fake_processor)
    client, app, source, _ = pg_client
    (source / "one.txt").write_text("Neutron calibration")
    store = app.state.inventory_store
    registered = store.register_source(source)
    store.new_scan(registered["id"], ScanOptions(readers=1, isolate=False))
    claimed = store.claim("test-scan")
    assert claimed
    execute(store, claimed, "test-scan", threading.Event())
    assert store.run(claimed["id"])["status"] == "done"
    with store.connect() as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        evidence = [tuple(r) for r in conn.execute("SELECT * FROM entries ORDER BY id")]
        links = [tuple(r) for r in conn.execute("SELECT * FROM main.sidecar_links")]
    selection = store.select(
        SelectionRequest(filters=Filters(source_id=registered["id"]))
    )
    response = client.post(
        "/api/runs", json={"inventory_selection_id": selection["id"]}
    )
    assert response.status_code == 200, response.text
    drain(app.state.postgres_workflow)
    assert store.entries(Filters(sidecar_state="processed"))["items"]
    assert not store.entries(Filters(sidecar_state="missing"))["items"]
    with store.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == version
        assert [
            tuple(r) for r in conn.execute("SELECT * FROM entries ORDER BY id")
        ] == evidence
        assert [
            tuple(r) for r in conn.execute("SELECT * FROM main.sidecar_links")
        ] == links
    assert (
        client.post(
            "/api/runs", json={"inventory_selection_id": selection["id"]}
        ).json()["id"]
        == response.json()["id"]
    )


def test_invalid_postgres_startup_never_falls_back_or_initializes(tmp_path, local_pg):
    from sqlalchemy import text

    with local_pg[1].begin() as conn:
        conn.execute(text("DROP TABLE osii_local_schema"))
    root = tmp_path / ".osii"
    root.mkdir()
    (root / "sentinel").write_text("Leave existing sidecars alone")
    with pytest.raises(RuntimeError, match="sidecars were not selected"):
        LibraryBackend(root, BackendSettings("postgres", local_pg[0]))
    assert list(root.iterdir()) == [root / "sentinel"]
    assert (root / "sentinel").read_text() == "Leave existing sidecars alone"
    with local_pg[1].connect() as conn:
        assert (
            conn.execute(text("SELECT to_regclass('osii_local_schema')")).scalar()
            is None
        )


def test_live_processor_http_baselines_work_offline_with_postgres(
    pg_client, monkeypatch
):
    """Real SDK HTTP clients, real baseline services; no containers or models."""
    from fastapi import FastAPI
    import importlib.util
    import socket
    import threading
    import time
    import uvicorn
    import subprocess
    import sys
    import signal
    from osii.domain.processing import postgres_workflow
    from osii.processor_sdk import ProcessorClient

    host = FastAPI()
    entered, release = threading.Event(), threading.Event()
    for kind, directory in (
        ("extractor", "local-extractor"),
        ("synthesizer", "local-synthesizer"),
        ("embedder", "local-embedder"),
        ("enricher", "local-enricher"),
    ):
        path = Path(__file__).parents[1] / "services" / directory / "app/main.py"
        spec = importlib.util.spec_from_file_location("pg_http_" + kind, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if kind == "extractor":
            original = module.LocalNativeTextExtractor.extract

            def gated_extract(self, request, original=original):
                if request.document.filename == "pending.txt":
                    entered.set()
                    release.wait(20)
                return original(self, request)

            monkeypatch.setattr(
                module.LocalNativeTextExtractor, "extract", gated_extract
            )
        host.mount("/" + kind, module.app)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(host, log_level="error", lifespan="off"))
    thread = threading.Thread(
        target=server.run, kwargs={"sockets": [sock]}, daemon=True
    )
    thread.start()
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    try:
        deadline = time.monotonic() + 5
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline
            time.sleep(0.01)

        def live_processor(root, name, kind):
            client = ProcessorClient(f"http://127.0.0.1:{port}/{kind}")
            return client.descriptor(), client

        monkeypatch.setattr(postgres_workflow, "processor", live_processor)
        client, app, source, runtime = pg_client
        (source / "example.txt").write_text(
            "Neutron detector calibration.\n\nThe experimental measurements were reproducible."
        )
        response = client.post(
            "/api/runs",
            json={
                "queue_paths": [str(source)],
                "synthesizer_name": "local.extractive-preview",
                "enricher_name": "local.stats-keywords",
                "build_embeddings": True,
                "embedder_name": "local.hashing",
                "embedding_model": "osii-local-hashing-v1",
            },
        )
        assert response.status_code == 200, response.text
        drain(app.state.postgres_workflow)
        run = client.get("/api/runs/" + response.json()["id"]).json()
        assert run["status"] == "done", run
        fid = client.get("/api/catalog/files").json()["items"][0]["file_id"]
        assert client.get(f"/api/objects/{fid}/source").status_code == 200
        assert client.get(f"/api/objects/{fid}/syntheses").json()["current_text"]
        answer = client.post(
            "/api/chat",
            json={"query": "What was calibrated?", "scope": {"scope_type": "root"}},
        )
        assert answer.status_code == 200, answer.text
        assert answer.json()["provider"] == "extractive" and answer.json()["citations"]
        assert client.get("/api/osii/files").json()["files"]
        assert not (runtime / "objects").exists()
        # Exercise the actual worker process, not just its in-process step
        # method. Interrupt an HTTP call; restart/retry must own a fresh claim.
        pending = source / "pending.txt"
        pending.write_text("A second detector measurement")
        submitted = client.post(
            "/api/runs", json={"queue_paths": [str(pending)]}
        ).json()
        env = {
            **os.environ,
            "PYTHONPATH": str(Path(__file__).parents[1]),
            "OSII_PROCESSORS": f"http://127.0.0.1:{port}/extractor",
            "OSII_START_TOOLBOX": "false",
        }
        flags = (
            {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
            if os.name == "nt"
            else {}
        )
        process = subprocess.Popen(
            [sys.executable, "-m", "osii.worker"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            **flags,
        )
        try:
            assert entered.wait(10), app.state.postgres_workflow.queue.get(
                submitted["id"]
            )
            process.send_signal(
                signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGTERM
            )
            output, _ = process.communicate(timeout=5)
            assert process.returncode == 0, output.decode(errors="replace")
            assert (
                app.state.postgres_workflow.queue.get(submitted["id"]).state == "queued"
            )
        finally:
            release.set()
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)
        drain(app.state.postgres_workflow)
        assert app.state.postgres_workflow.queue.get(submitted["id"]).state == "done"
        assert client.get("/api/catalog/files").json()["total"] == 2
    finally:
        release.set()
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
        assert not thread.is_alive()


def test_semantic_queries_require_matching_endpoint_model_and_dimensions(
    pg_client, monkeypatch
):
    from osii.domain.processing import postgres_workflow
    from osii.processors import remote
    import osii.processor_sdk as sdk

    file_id, _ = intake(pg_client, monkeypatch)
    client, app, source, _ = pg_client
    address = ["http://embedding.test"]
    dimensions = [2]

    def providers(root, name, kind):
        descriptor, service = fake_processor(root, name, kind)
        service.base_url = address[0]
        old = service.embed

        def embed(request):
            response = old(request)
            if dimensions[0] != 2:
                response = response.model_copy(
                    update={
                        "vectors": [
                            sdk.EmbeddingVector(
                                id=v.id, vector=[1.0, 0.0, 0.0], dimensions=3
                            )
                            for v in response.vectors
                        ]
                    }
                )
            return response

        service.embed = embed
        return descriptor, service

    monkeypatch.setattr(postgres_workflow, "processor", providers)
    flow = app.state.postgres_workflow
    flow.submit_files(
        [source / "one.txt"],
        {
            "run_extraction": False,
            "build_embeddings": True,
            "embedder_name": "test.embedder",
            "embedding_model": "test-model",
        },
        shared_root=source,
        upload_root=source,
    )
    drain(flow)
    descriptor, service = providers(None, "test.embedder", "embedder")
    monkeypatch.setattr(
        remote,
        "resolve_remote_processor",
        lambda *a: {**descriptor.model_dump(mode="json"), "base_url": address[0]},
    )
    monkeypatch.setattr(
        sdk,
        "ProcessorClient",
        lambda *a, **kw: providers(None, "test.embedder", "embedder")[1],
    )
    payload = {"query": "calibration", "mode": "semantic"}
    result = client.post("/api/search", json=payload)
    assert (
        result.status_code == 200 and result.json()["retrieval_mode_used"] == "semantic"
    ), result.text
    dimensions[0] = 3
    assert client.post("/api/search", json=payload).status_code == 422
    hybrid = client.post("/api/search", json={**payload, "mode": "hybrid"})
    assert (
        hybrid.status_code == 200 and hybrid.json()["retrieval_mode_used"] == "lexical"
    )
    dimensions[0] = 2
    address[0] = "http://different-embedding.test"
    assert client.post("/api/search", json=payload).status_code == 422
    # No silent reindex into a different endpoint's vector space.
    job = flow.submit_files(
        [source / "one.txt"],
        {
            "run_extraction": False,
            "build_embeddings": True,
            "embedder_name": "test.embedder",
            "embedding_model": "test-model",
        },
        shared_root=source,
        upload_root=source,
    )
    claim = flow.queue.claim("test")
    flow.step(claim.lease)
    claim = flow.queue.claim("test")
    with pytest.raises(ValueError, match="rebuild"):
        flow.step(claim.lease)
    flow.queue.finish(claim.lease, error="Rebuild required")
    assert app.state.postgres_library.query("SELECT embedding FROM chunks")[0][
        "embedding"
    ] == [1.0, 0.0]
    assert job.state == "queued"
    dimensions[0] = 3
    rebuilt = flow.submit_files(
        [source / "one.txt"],
        {
            "run_extraction": False,
            "build_embeddings": True,
            "embedder_name": "test.embedder",
            "embedding_model": "test-model",
            "rebuild_embeddings": True,
        },
        shared_root=source,
        upload_root=source,
    )
    drain(flow)
    assert flow.queue.get(rebuilt.job_id).state == "done"
    assert all(
        len(r["embedding"]) == 3
        for r in app.state.postgres_library.query("SELECT embedding FROM chunks")
    )
    assert client.post("/api/search", json=payload).status_code == 200


def test_import_preserves_all_scope_human_histories_and_builds_lexical_chunks(
    local_pg, tmp_path
):
    from osii.domain.artifacts.products import publish_product, product_path
    from osii.domain.storage.sidecar_import import plan_import, apply_import
    from osii.domain.storage.postgres_library import PostgresLibrary
    from osii.domain.storage.authoring import ProductRef
    from osii.domain.read.contracts import ReadScope
    from osii.domain.storage.retrieval import RetrievalRequest
    import tomli_w

    root = tmp_path / ".osii"
    seed(root)
    folders = root / "folders"
    folders.mkdir()
    (folders / "folder-reports.toml").write_text(
        tomli_w.dumps({"node": {"folder_id": "reports", "path_hint": "reports"}})
    )
    scopes = [
        {"scope_type": "root"},
        {"scope_type": "object", "file_id": "sha256-a"},
        {"scope_type": "folder", "folder_id": "reports"},
        {"scope_type": "collection", "collection_id": "col-test"},
    ]
    for scope in scopes:
        path = product_path(root, scope, "wiki--test.json")
        publish_product(
            root,
            path,
            {
                "artifact_type": "wiki_markdown",
                "title": "Wiki",
                "markdown": "# Generated",
                "citations": [{"file_id": "sha256-a", "page": 1}],
            },
        )
        publish_product(
            root,
            path,
            {
                "artifact_type": "wiki_markdown",
                "title": "Wiki",
                "markdown": "# Human edited",
                "citations": [{"file_id": "sha256-a", "page": 1}],
            },
            origin="human",
        )
    before = {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file()
    }
    apply_import(local_pg[1], plan_import(root))
    backend = LibraryBackend(
        tmp_path / "runtime", BackendSettings("postgres", local_pg[0])
    )
    try:
        lib = PostgresLibrary(backend)
        for scope in scopes:
            read = lib.scope(scope)
            history = backend.products.history(ProductRef(read, "wiki--test.json"))
            assert (
                history.active.origin == "human"
                and history.active.data["markdown"] == "# Human edited"
            )
            assert (
                len(history.revisions) == 2
                and history.active.data["citations"][0]["page"] == 1
            )
        assert lib.retrieve(
            RetrievalRequest(
                "human corrected", ReadScope("object", "sha256-a"), "lexical"
            )
        ).hits
        artifacts = backend.reader.list_artifacts("sha256-a").items
        assert (
            sum(a.title == "Wiki" for a in artifacts) == 2
        )  # pre-existing wiki + versioned wiki
        assert before == {
            p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob("*")
            if p.is_file()
        }
    finally:
        backend.close()


def test_storage_cli_hides_connection_errors(monkeypatch, capsys):
    from osii import storage_cli

    monkeypatch.setenv("OSII_STORAGE_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:private-password@host/db")

    def failed(*a):
        raise RuntimeError("private-password")

    monkeypatch.setattr(storage_cli, "postgres_engine", failed)
    with pytest.raises(SystemExit) as exc:
        storage_cli.main(["status"])
    assert exc.value.code == 2
    assert "private-password" not in capsys.readouterr().err


@pytest.mark.parametrize("local_pg", [False], indirect=True)
def test_explicit_cli_init_preview_apply_and_status(
    local_pg, tmp_path, monkeypatch, capsys
):
    from osii.storage_cli import main

    monkeypatch.setenv("OSII_STORAGE_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", local_pg[0])
    root = tmp_path / ".osii"
    before = seed(root)
    assert main(["init"]) == 0
    assert json.loads(capsys.readouterr().out)["initialized"] is True
    assert main(["status"]) == 0
    assert json.loads(capsys.readouterr().out)["schema_ready"] is True
    assert main(["import-sidecars", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["imported"] is False
    assert main(["import-sidecars", str(root), "--apply"]) == 0
    assert json.loads(capsys.readouterr().out)["documents"] == 3
    with pytest.raises(SystemExit) as exc:
        main(["init"])
    assert exc.value.code == 2 and "empty" in capsys.readouterr().err
    assert before == {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file()
    }


def test_setup_uses_the_selected_library_readiness(pg_client, monkeypatch):
    from test_setup_api import _offline_readiness
    from osii.api import setup_routes

    client, app, _, _ = pg_client
    result = {
        **_offline_readiness(),
        "storage_backend": "postgres",
        "semantic_indexes": [{"index_id": "postgres-only"}],
    }
    app.state.intake_readiness = lambda request: result
    monkeypatch.setattr(setup_routes, "_services", lambda: (False, []))
    response = client.get("/api/admin/setup")
    assert response.status_code == 200, response.text
    assert response.json()["readiness"]["semantic_indexes"] == [
        {"index_id": "postgres-only"}
    ]


def test_staged_run_budget_pauses_between_steps_and_resume_gets_new_budget(
    pg_client, monkeypatch
):
    import time
    from osii.domain.processing import postgres_workflow

    monkeypatch.setattr(postgres_workflow, "processor", fake_processor)
    client, app, source, _ = pg_client
    (source / "one.txt").write_text("Neutron calibration")
    job = client.post("/api/runs", json={"queue_paths": [str(source)]}).json()
    flow = app.state.postgres_workflow
    claim = flow.queue.claim("test")
    flow.step(claim.lease)
    claim = flow.queue.claim("test")
    flow._update_root(
        claim.lease,
        lambda p: p.update(
            staging={"max_seconds": 1}, budget_started_at=time.time() - 2
        ),
    )
    flow.step(claim.lease)
    assert flow.queue.get(job["id"]).state == "paused"
    assert client.get("/api/catalog/files").json()["total"] == 1
    assert client.post(f"/api/runs/{job['id']}/resume").status_code == 200
    drain(flow)
    assert flow.queue.get(job["id"]).state == "done"


@pytest.mark.parametrize("kind", ["root", "folder", "collection"])
def test_workbench_aggregate_synthesis_and_enrichment(pg_client, monkeypatch, kind):
    file_id, _ = intake(pg_client, monkeypatch)
    client, app, _, _ = pg_client
    lib = app.state.postgres_library
    if kind == "collection":
        record = lib.backend.collections.create("Aggregate")
        lib.backend.collections.replace_members(
            record.collection_id, [file_id], expected_version=record.version
        )
        scope = {"scope_type": kind, "collection_id": record.collection_id}
    elif kind == "folder":
        scope = {"scope_type": kind, "folder_id": lib.folders()[0]["folder_id"]}
    else:
        scope = {"scope_type": "root"}
    flow = app.state.postgres_workflow
    for capability, name in (
        ("synthesizer", "test.preview"),
        ("enricher", "test.stats"),
    ):
        flow.submit_scope(
            scope, name, capability, expert_context="Measurements are calibrated."
        )
        drain(flow)
    assert lib.synthesis(scope) == "# A grounded summary"
    assert any(p["artifact_type"] == "table" for p in lib.enrichments(scope))
    overview = client.post("/api/scopes/overview", json=scope)
    assert overview.status_code == 200 and overview.json()["file_count"] == 1


def test_reextraction_variants_and_promotion_preserve_corrections(
    pg_client, monkeypatch
):
    from osii.domain.processing import postgres_workflow
    from osii.processor_sdk import TextSegment

    file_id, _ = intake(pg_client, monkeypatch)
    client, app, source, _ = pg_client
    lib = app.state.postgres_library
    canonical = lib.reader.get_representation(file_id, "canonical").text
    saved = lib.backend.text.save(
        file_id,
        [{"id": "seg-000001", "text": "Human reviewed content"}],
        expected_revision=None,
    )

    def better(root, name, kind):
        descriptor, service = fake_processor(root, name, kind)
        old = service.extract
        service.extract = lambda request: old(request).model_copy(
            update={
                "segments": [
                    TextSegment(
                        id="page-2",
                        text="Better grounded OCR",
                        source_origin={"page": 2, "bbox": [0.1, 0.2, 0.5, 0.6]},
                    )
                ]
            }
        )
        return descriptor, service

    monkeypatch.setattr(postgres_workflow, "processor", better)
    response = client.post(
        f"/api/objects/{file_id}/extractions",
        json={"extractor_name": "test.better", "extraction_policy": "save_variant"},
    )
    assert response.status_code == 200, response.text
    drain(app.state.postgres_workflow)
    assert lib.reader.get_representation(file_id).text == saved.text
    assert lib.reader.get_representation(file_id, "canonical").text == canonical
    alternate = next(
        r
        for r in lib.query("SELECT id,response FROM extractions")
        if r["response"]["processor"]["name"] == "test.better"
    )
    promoted = client.post(
        f"/api/objects/{file_id}/extractions/{alternate['id']}/primary"
    )
    assert promoted.status_code == 200, promoted.text
    preferred = lib.reader.get_representation(file_id)
    assert (
        preferred.text == "Better grounded OCR"
        and preferred.segments[0].source_origin["page"] == 2
    )
    history = lib.query(
        "SELECT metadata->'edited_text_history' AS history FROM documents"
    )[0]["history"]
    assert len(history) == 1 and history[0]["text"] == saved.text
    assert (
        client.get(f"/api/objects/{file_id}").json()["processing"]["extractor"]["name"]
        == "test.better"
    )
    assert (source / "one.txt").read_text() in canonical
