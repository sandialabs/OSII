"""The same processing commit contract against sidecars and real PostgreSQL."""
from __future__ import annotations

import base64
from dataclasses import replace
import hashlib
import json

import pytest

from test_library_reads import postgres_reader
from osii.domain.read.contracts import ReadScope
from osii.domain.storage.commits import (CommitConflict, InputRevision, JobCheckpoint,
    ProcessingCommit, SourceRecord, ScopeInputRevision, ScopeProcessingCommit, text_digest)
from osii.processor_sdk import (Artifact, Capability, DocumentInput, EmbeddingInput,
    EmbeddingRequest, EmbeddingResponse, EmbeddingVector, EnrichmentRequest,
    EnrichmentResponse, ExtractionRequest, ExtractionResponse, ModelContext,
    ProcessorDescriptor, ProcessorKind, ProvenanceRef, ScopeInput, SynthesisRequest,
    SynthesisResponse, TableArtifactData, TableColumn, TextSegment, WikiMarkdownArtifactData)

RAW = b"original source bytes"
SHA = hashlib.sha256(RAW).hexdigest()
FILE_ID = "sha256-" + SHA
TEXT = "Neutron detector.\nCalibration results."
ORIGIN = {"page": 1, "bbox": [0.1, 0.2, 0.8, 0.4]}


def descriptor(kind):
    return ProcessorDescriptor(name="test." + kind, version="1", display_name="Test " + kind,
        description="Contract fixture", kind=ProcessorKind(kind), capabilities=Capability(scope_types=["object"]))


def extraction(operation="extract", text=TEXT, primary=True):
    producer = descriptor("extractor")
    request = ExtractionRequest(request_id="request-" + operation, document=DocumentInput(file_id=FILE_ID,
        filename="report.pdf", content_base64=base64.b64encode(RAW).decode()))
    response = ExtractionResponse(request_id=request.request_id, processor=producer,
        segments=[TextSegment(id="source-segment", text=text, source_origin=ORIGIN)])
    return ProcessingCommit(operation, FILE_ID, request, response, producer,
        source=SourceRecord(FILE_ID, "reports/report.pdf", "report.pdf", "application/pdf", SHA, len(RAW)),
        make_primary=primary, chunks=({"chunk_id": "chunk-1", "file_id": FILE_ID,
            "text": text, "char_start": 0, "char_end": len(text), "source_origin": ORIGIN},))


def derived(reader, kind="synthesis", operation=None):
    revision = InputRevision.capture(reader, FILE_ID)
    producer = descriptor("synthesizer" if kind == "synthesis" else "enricher")
    scope = ScopeInput(scope_type="object", scope_id=FILE_ID,
        documents=[DocumentInput(file_id=FILE_ID, filename="report.pdf", text=reader.get_representation(FILE_ID).text)])
    if kind == "synthesis":
        request = SynthesisRequest(request_id="synthesize-request", scope=scope, expert_context="Units are kelvin.")
        response = SynthesisResponse(request_id=request.request_id, processor=producer,
            markdown="# Detector\nGrounded account.", citations=[ProvenanceRef(file_id=FILE_ID, char_start=0, char_end=7)])
    else:
        request = EnrichmentRequest(request_id="enrich-request", scope=scope)
        response = EnrichmentResponse(request_id=request.request_id, processor=producer, artifacts=[
            Artifact(id="statistics", kind="table", media_type="application/json",
                standard_data=TableArtifactData(title="Statistics", columns=[TableColumn(key="words", label="Words", data_type="integer")], rows=[{"words": 4}])),
            Artifact(id="wiki", kind="wiki_markdown", media_type="application/json",
                standard_data=WikiMarkdownArtifactData(title="Wiki", markdown="# Detector", citations=[ProvenanceRef(file_id=FILE_ID)]))])
    return ProcessingCommit(operation or kind, FILE_ID, request, response, producer, input_revision=revision)


@pytest.fixture(params=["sidecar", "postgres"])
def backend(request, tmp_path):
    if request.param == "sidecar":
        pytest.importorskip("osii.domain.artifacts.products", reason="Sidecar product history belongs to OSII-local")
        from osii.domain.read.sidecar import SidecarLibraryReader
        from osii.domain.storage.sidecar_commits import SidecarProcessingCommitter
        root = tmp_path / ".osii"
        return SidecarProcessingCommitter(root), SidecarLibraryReader(root)
    reader = request.getfixturevalue("postgres_reader")
    from sqlalchemy import text
    from osii.domain.storage.postgres_commits import PostgresProcessingCommitter
    with reader.engine.begin() as conn:
        conn.execute(text("ALTER TABLE documents ADD COLUMN updated_at timestamptz DEFAULT now()"))
        conn.execute(text("ALTER TABLE extractions ADD COLUMN sha256 text"))
        conn.execute(text("CREATE TABLE chunks(chunk_id text PRIMARY KEY, file_id text, text text, char_start int, char_end int, source_origin jsonb, embedding jsonb, embedding_model text)"))
        conn.execute(text("CREATE TABLE settings(id text PRIMARY KEY, value jsonb NOT NULL)"))
        conn.execute(text("CREATE TABLE datasets(id text PRIMARY KEY, revision int)"))
        conn.execute(text("INSERT INTO datasets VALUES ('shared',0)"))
        conn.execute(text("CREATE TABLE jobs(id text PRIMARY KEY, worker_id text, status text, lease_until timestamptz, payload jsonb)"))
        conn.execute(text("""CREATE TABLE scope_products(id text PRIMARY KEY,scope_type text,scope_id text,
            filename text,family text,method text,current_revision text,title text,artifact_type text,
            CONSTRAINT scope_product_address UNIQUE(scope_type,scope_id,filename))"""))
        conn.execute(text("""CREATE TABLE scope_revisions(id text PRIMARY KEY,product_id text REFERENCES scope_products(id),
            parent text,origin text,created_at text,actor_id text,data jsonb,provenance jsonb)"""))
    return PostgresProcessingCommitter(reader.engine), reader


def test_extraction_is_idempotent_preserves_geometry_and_variants(backend):
    writer, reader = backend
    command = extraction()
    saved = writer.commit(command)
    assert saved.file_id == FILE_ID and saved.kind == "extraction"
    assert saved.result["variant_id"] == command.commit_id
    assert writer.commit(command).replayed
    assert reader.get_representation(FILE_ID).text == TEXT
    assert reader.get_representation(FILE_ID).segments[0].source_origin["bbox"] == ORIGIN["bbox"]
    alternate = extraction("alternate", "Better OCR.", primary=False)
    writer.commit(alternate)
    assert reader.get_representation(FILE_ID).text == TEXT
    assert reader.get_representation(FILE_ID, alternate.commit_id).text == "Better OCR."


def test_synthesis_and_enrichment_commit_once_with_lineage(backend):
    writer, reader = backend
    writer.commit(extraction())
    for kind in ("synthesis", "enrichment"):
        command = derived(reader, kind)
        receipt = writer.commit(command)
        before = reader.list_artifacts(FILE_ID).total
        assert writer.commit(command).replayed
        assert reader.list_artifacts(FILE_ID).total == before
        assert receipt.file_id == FILE_ID and receipt.kind == kind
    assert reader.get_representation(FILE_ID).text == TEXT


def test_stale_inputs_and_reused_ids_do_not_overwrite_newer_work(backend):
    writer, reader = backend
    writer.commit(extraction())
    old = derived(reader)
    writer.commit(extraction("replacement", "New evidence."))
    with pytest.raises(CommitConflict, match="changed"):
        writer.commit(old)
    assert reader.get_representation(FILE_ID).text == "New evidence."
    fresh = derived(reader)
    writer.commit(fresh)
    changed = replace(fresh, response=fresh.response.model_copy(update={"markdown": "Different result"}))
    with pytest.raises(CommitConflict, match="Operation ID"):
        writer.commit(changed)


def test_wrong_response_identity_and_citations_fail_before_writes(backend):
    writer, reader = backend
    initial = extraction()
    bad = replace(initial, response=initial.response.model_copy(update={"request_id": "wrong"}))
    with pytest.raises(ValueError, match="match"):
        writer.commit(bad)
    assert reader.get_document(FILE_ID) is None
    writer.commit(initial)
    command = derived(reader)
    bad = replace(command, response=command.response.model_copy(update={"citations": [ProvenanceRef(file_id="other-document")]}))
    with pytest.raises(ValueError, match="scope"):
        writer.commit(bad)
    assert not reader.list_artifacts(FILE_ID).items


def test_embedding_vectors_and_identity_are_validated_and_saved(backend):
    writer, reader = backend
    writer.commit(extraction())
    producer = descriptor("embedder")
    request = EmbeddingRequest(request_id="embed", inputs=[EmbeddingInput(id="chunk-1", text=TEXT)], config={"model": "test-model"})
    response = EmbeddingResponse(request_id="embed", processor=producer, model="test-model", normalized=True,
        vectors=[EmbeddingVector(id="chunk-1", vector=[1.0, 0.0], dimensions=2)])
    command = ProcessingCommit("embedding", FILE_ID, request, response, producer,
        input_revision=InputRevision.capture(reader, FILE_ID))
    saved = writer.commit(command)
    assert saved.result["identity"]["model"] == "test-model"
    assert saved.result["identity"]["dimensions"] == 2
    assert writer.commit(command).replayed
    bad = replace(command, operation_id="bad-embed", response=response.model_copy(update={"vectors": [EmbeddingVector(id="wrong", vector=[1., 0.], dimensions=2)]}))
    with pytest.raises(ValueError, match="IDs"):
        writer.commit(bad)
    for vector in ([float("nan"), 0.], [3., 0.]):
        invalid = replace(command, operation_id="invalid-vector", response=response.model_copy(update={
            "vectors": [EmbeddingVector(id="chunk-1", vector=vector, dimensions=2)]}))
        with pytest.raises(ValueError):
            writer.commit(invalid)


def test_job_checkpoint_rolls_back_with_the_result(backend):
    writer, reader = backend
    if not hasattr(reader, "engine"):
        pytest.skip("Local job state is a separate operational store")
    from sqlalchemy import text
    writer.commit(extraction())
    command = derived(reader)
    with reader.engine.begin() as conn:
        conn.execute(text("INSERT INTO jobs VALUES ('job','worker','running',now()+interval '1 minute','{\"items\":[{}]}')"))
    with pytest.raises(ValueError, match="outside"):
        writer.commit(command, checkpoint=JobCheckpoint("job", "worker", 9, {"status": "done"}))
    assert reader.list_artifacts(FILE_ID).total == 0
    with pytest.raises(CommitConflict, match="owns"):
        writer.commit(command, checkpoint=JobCheckpoint("job", "wrong-worker", 0, {"status": "done"}))
    with reader.engine.begin() as conn:
        conn.execute(text("UPDATE jobs SET lease_until=now()-interval '1 minute' WHERE id='job'"))
    with pytest.raises(CommitConflict, match="owns"):
        writer.commit(command, checkpoint=JobCheckpoint("job", "worker", 0, {"status": "done"}))
    with reader.engine.begin() as conn:
        conn.execute(text("UPDATE jobs SET lease_until=now()+interval '1 minute' WHERE id='job'"))
    writer.commit(command, checkpoint=JobCheckpoint("job", "worker", 0, {"status": "done"}))
    with reader.engine.connect() as conn:
        assert conn.execute(text("SELECT payload FROM jobs WHERE id='job'")).scalar()["items"][0]["status"] == "done"


def test_sidecar_interrupted_receipt_and_partial_products_resume(tmp_path, monkeypatch):
    pytest.importorskip("osii.domain.artifacts.products")
    from osii.domain.read.sidecar import SidecarLibraryReader
    from osii.domain.storage import sidecar_commits
    from osii.domain.artifacts import products
    root = tmp_path / ".osii"
    writer, reader = sidecar_commits.SidecarProcessingCommitter(root), SidecarLibraryReader(root)
    original = sidecar_commits.atomic_write_text
    def interrupted(path, data):
        if path.parent.name == "runs":
            raise OSError("Simulated interruption before step receipt")
        return original(path, data)
    with monkeypatch.context() as patch:
        patch.setattr(sidecar_commits, "atomic_write_text", interrupted)
        with pytest.raises(OSError):
            writer.commit(extraction())
    writer.commit(extraction())
    assert len(json.loads((root / "objects" / FILE_ID / "extractions/index.json").read_text())["variants"]) == 1
    command = derived(reader, "enrichment")
    original_publish = products.publish_product
    def partial(root, path, data, **kwargs):
        if data.get("artifact_type") == "wiki_markdown":
            raise OSError("Simulated interrupted second product")
        return original_publish(root, path, data, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(products, "publish_product", partial)
        with pytest.raises(OSError):
            writer.commit(command)
    writer.commit(command)
    history = products.read_product(root / "objects" / FILE_ID / "enrichments/table--test.enricher.json")
    assert len(history["revisions"]) == 1
    assert history["revisions"][0]["provenance"]["input_text_sha256"] == text_digest(TEXT)


def test_model_gateway_tokens_never_enter_commit_storage(backend):
    writer, reader = backend
    writer.commit(extraction())
    command = derived(reader)
    command.request.model_context = ModelContext(gateway_url="http://localhost/v1", token="secret-job-token", bindings={"chat": "top"})
    writer.commit(command)
    if hasattr(reader, "root"):
        assert all(b"secret-job-token" not in path.read_bytes() for path in reader.root.rglob("*") if path.is_file())
    else:
        from sqlalchemy import text
        with reader.engine.connect() as conn:
            assert "secret-job-token" not in str(conn.execute(text("SELECT payload FROM artifacts WHERE file_id=:id"), {"id": FILE_ID}).all())
            assert "secret-job-token" not in str(conn.execute(text("SELECT value FROM settings")).all())


def test_new_generated_commit_preserves_a_human_product_revision(tmp_path):
    pytest.importorskip("osii.domain.artifacts.products")
    from osii.domain.read.sidecar import SidecarLibraryReader
    from osii.domain.storage.sidecar_commits import SidecarProcessingCommitter
    from osii.domain.artifacts.products import publish_product, read_product
    root = tmp_path / ".osii"
    writer, reader = SidecarProcessingCommitter(root), SidecarLibraryReader(root)
    writer.commit(extraction())
    writer.commit(derived(reader))
    path = root / "objects" / FILE_ID / "synth.txt"
    human = {"artifact_type": "text", "title": "Summary", "text": "A human correction."}
    publish_product(root, path, human, origin="human")
    writer.commit(derived(reader, operation="regenerate"))
    result = read_product(path)
    assert result["data"] == human
    assert len(result["revisions"]) == 3


def test_extraction_retry_after_lost_receipt_does_not_reactivate_old_text(tmp_path, monkeypatch):
    pytest.importorskip("osii.domain.artifacts.products")
    from osii.domain.read.sidecar import SidecarLibraryReader
    from osii.domain.storage import sidecar_commits
    root = tmp_path / ".osii"
    writer, reader = sidecar_commits.SidecarProcessingCommitter(root), SidecarLibraryReader(root)
    original = sidecar_commits.atomic_write_text
    def lost(path, data):
        if path.parent.name == "runs":
            raise OSError("Lost receipt")
        return original(path, data)
    with monkeypatch.context() as patch:
        patch.setattr(sidecar_commits, "atomic_write_text", lost)
        with pytest.raises(OSError):
            writer.commit(extraction())
    writer.commit(extraction("newer", "New preferred text."))
    writer.commit(extraction())
    assert reader.get_representation(FILE_ID).text == "New preferred text."


@pytest.fixture
def scoped_backend(backend):
    writer, reader = backend
    writer.commit(extraction())
    if hasattr(reader, "root"):
        import tomli_w
        folder = reader.root / "folders"
        folder.mkdir(exist_ok=True)
        (folder / "folder-reports.toml").write_text(tomli_w.dumps({"node": {
            "folder_id": "reports", "path_hint": "reports"}}), encoding="utf-8")
        collection = reader.root / "collections" / "col-aggregate"
        collection.mkdir(parents=True)
        (collection / "collection.toml").write_text('[collection]\nid = "col-aggregate"\nname = "Reports"\n', encoding="utf-8")
        (collection / "members.jsonl").write_text(json.dumps({"file_id": FILE_ID}) + "\n", encoding="utf-8")
    else:
        from sqlalchemy import text
        with reader.engine.begin() as conn:
            conn.execute(text("INSERT INTO collections VALUES ('col-aggregate',CAST(:members AS jsonb),'shared',null)"),
                         {"members": json.dumps([FILE_ID])})
    return writer, reader


def scope_command(backend, scope_kind="root", kind="enrichment", operation="scope-product"):
    writer, reader = backend
    scope = ReadScope(scope_kind, {"root": "root", "folder": "reports", "collection": "col-aggregate"}[scope_kind])
    members = [row.file_id for row in reader.list_documents(scope, limit=500).items]
    revision = ScopeInputRevision.capture(reader, members)
    template = derived(reader, kind)
    producer = template.expected_processor.model_copy(update={"capabilities": Capability(scope_types=["root", "folder", "collection"])})
    documents = [DocumentInput(file_id=row.file_id, filename=row.file_id,
        text=reader.get_representation(row.file_id).text[:12]) for row in revision.inputs]
    request = template.request.model_copy(update={"scope": ScopeInput(scope_type=scope.kind,
        scope_id=scope.identifier, documents=documents)})
    response = template.response.model_copy(update={"processor": producer})
    return ScopeProcessingCommit(operation, scope, request, response, producer, revision)


def scope_history(backend, command):
    writer, reader = backend
    if hasattr(reader, "root"):
        from osii.domain.artifacts.products import product_path, read_product
        from osii.domain.artifacts.enrichment_artifacts import _scope_enrichment_dir
        scope = writer._scope(command)
        if command.kind == "synthesis":
            paths = [product_path(reader.root, scope, command.expected_processor.name + ".txt", "synthesis")]
        else:
            directory = _scope_enrichment_dir(reader.root, scope)[1]
            paths = list(directory.glob("*.json"))
            paths = [path for path in paths if not path.name.endswith(".meta.json")]
        return [dict(read_product(path), filename=path.name) for path in paths if path.is_file()]
    from sqlalchemy import text
    with reader.engine.connect() as conn:
        products = conn.execute(text("SELECT * FROM scope_products WHERE scope_type=:kind AND scope_id=:id ORDER BY filename"),
            {"kind": command.scope.kind, "id": command.scope.identifier}).mappings().all()
        result = []
        for product in products:
            revisions = [dict(row) for row in conn.execute(text("SELECT * FROM scope_revisions WHERE product_id=:id ORDER BY created_at,id"),
                {"id": product["id"]}).mappings()]
            current = next(row for row in revisions if row["id"] == product["current_revision"])
            result.append({"filename": product["filename"], "current": current["id"], "data": current["data"], "revisions": revisions})
        return result


@pytest.mark.parametrize("scope_kind", ["folder", "collection", "root"])
@pytest.mark.parametrize("kind", ["synthesis", "enrichment"])
def test_scope_products_commit_once_with_full_input_lineage(scoped_backend, scope_kind, kind):
    writer, reader = scoped_backend
    command = scope_command(scoped_backend, scope_kind, kind)
    saved = writer.commit(command)
    assert saved.file_id is None and saved.scope_type == scope_kind
    assert saved.scope_id == command.scope.identifier
    assert writer.commit(command).replayed
    histories = scope_history(scoped_backend, command)
    assert len(histories) == (1 if kind == "synthesis" else 2)
    assert all(len(item["revisions"]) == 1 for item in histories)
    for history in histories:
        provenance = history["revisions"][0]["provenance"]
        assert provenance["commit_id"] == command.commit_id
        inputs = {row["file_id"]: row for row in provenance["processing_input"]["inputs"]}
        assert inputs[FILE_ID]["text_sha256"] == text_digest(TEXT)
    assert reader.get_representation(FILE_ID).text == TEXT
    altered = replace(command, provenance={"different": True})
    with pytest.raises(CommitConflict, match="Operation ID"):
        writer.commit(altered)


@pytest.mark.parametrize("scope_kind", ["folder", "collection", "root"])
def test_scope_rejects_changed_full_text_even_outside_the_excerpt(scoped_backend, scope_kind):
    writer, reader = scoped_backend
    command = scope_command(scoped_backend, scope_kind)
    writer.commit(extraction("replacement", TEXT + " New ending outside the excerpt."))
    with pytest.raises(CommitConflict, match="input text changed"):
        writer.commit(command)
    assert not scope_history(scoped_backend, command)


def test_scope_rejects_membership_change_before_publishing(scoped_backend):
    writer, reader = scoped_backend
    command = scope_command(scoped_backend, "collection")
    if hasattr(reader, "root"):
        (reader.root / "collections/col-aggregate/members.jsonl").write_text("", encoding="utf-8")
    else:
        from sqlalchemy import text
        with reader.engine.begin() as conn:
            conn.execute(text("UPDATE collections SET members='[]' WHERE id='col-aggregate'"))
    with pytest.raises(CommitConflict, match="membership changed"):
        writer.commit(command)
    assert not scope_history(scoped_backend, command)


@pytest.mark.parametrize("scope_kind", ["root", "folder"])
def test_scope_detects_new_members_even_with_an_old_catalog(scoped_backend, scope_kind):
    writer, reader = scoped_backend
    command = scope_command(scoped_backend, scope_kind)
    added = extraction("new-member")
    new_id = "sha256-new-member"
    added = replace(added, file_id=new_id,
        request=added.request.model_copy(update={"document": added.request.document.model_copy(update={"file_id": new_id})}),
        source=replace(added.source, file_id=new_id, source_relpath="reports/new.pdf"),
        chunks=())
    writer.commit(added)
    with pytest.raises(CommitConflict, match="membership changed"):
        writer.commit(command)
    assert not scope_history(scoped_backend, command)


def test_scope_validation_checks_request_scope_excerpt_citations_and_tokens(scoped_backend):
    writer, reader = scoped_backend
    command = scope_command(scoped_backend, kind="synthesis")
    wrong_scope = replace(command, scope=ReadScope("collection", "another-collection"))
    with pytest.raises(ValueError, match="match.*scope"):
        writer.commit(wrong_scope)
    for citation in [ProvenanceRef(file_id="not-an-input"), ProvenanceRef(file_id=FILE_ID, char_start=0, char_end=len(TEXT))]:
        bad = replace(command, response=command.response.model_copy(update={"citations": [citation]}))
        with pytest.raises(ValueError, match="scope|supplied text"):
            writer.commit(bad)
    assert not scope_history(scoped_backend, command)
    command.request.model_context = ModelContext(gateway_url="http://localhost/v1", token="secret-scope-token", bindings={"chat": "top"})
    writer.commit(command)
    assert "secret-scope-token" not in str(scope_history(scoped_backend, command))
    command.request.model_context.token = "replacement-token"
    assert writer.commit(command).replayed


def test_scope_checkpoint_failure_rolls_back_all_products(scoped_backend):
    writer, reader = scoped_backend
    if not hasattr(reader, "engine"):
        pytest.skip("Local queue state remains separately owned")
    from sqlalchemy import text
    command = scope_command(scoped_backend)
    with reader.engine.begin() as conn:
        conn.execute(text("INSERT INTO jobs VALUES ('scope-job','worker','running',now()+interval '1 minute','{\"items\":[{}]}')"))
    with pytest.raises(ValueError, match="outside"):
        writer.commit(command, checkpoint=JobCheckpoint("scope-job", "worker", 5, {"status": "done"}))
    assert not scope_history(scoped_backend, command)
    writer.commit(command, checkpoint=JobCheckpoint("scope-job", "worker", 0, {"status": "done"}))
    assert len(scope_history(scoped_backend, command)) == 2
    with reader.engine.connect() as conn:
        assert conn.execute(text("SELECT payload FROM jobs WHERE id='scope-job'")).scalar()["items"][0]["status"] == "done"


def test_scope_regeneration_keeps_human_revision_current(scoped_backend):
    writer, reader = scoped_backend
    command = scope_command(scoped_backend, kind="synthesis")
    writer.commit(command)
    history = scope_history(scoped_backend, command)[0]
    if hasattr(reader, "root"):
        from osii.domain.artifacts.products import product_path, publish_product
        path = product_path(reader.root, writer._scope(command), history["filename"], "synthesis")
        publish_product(reader.root, path, {"artifact_type": "text", "title": "Summary", "text": "Human correction"}, origin="human")
    else:
        from sqlalchemy import text
        with reader.engine.begin() as conn:
            conn.execute(text("""INSERT INTO scope_revisions SELECT 'human',product_id,:parent,'human','now',null,
                CAST(:data AS jsonb),'{}' FROM scope_revisions WHERE id=:parent"""),
                {"parent": history["current"], "data": json.dumps({"artifact_type": "wiki_markdown", "title": "Reviewed", "markdown": "Human correction"})})
            conn.execute(text("UPDATE scope_products SET current_revision='human' WHERE current_revision=:parent"), {"parent": history["current"]})
    human = scope_history(scoped_backend, command)[0]
    writer.commit(replace(command, operation_id="scope-regeneration", product_parents={human["filename"]: human["current"]}))
    latest = scope_history(scoped_backend, command)[0]
    assert latest["current"] == human["current"]
    assert len(latest["revisions"]) == 3


def test_scope_parent_guard_and_completed_retry_do_not_reactivate_old_products(scoped_backend):
    writer, reader = scoped_backend
    initial = scope_command(scoped_backend, kind="synthesis")
    writer.commit(initial)
    first = scope_history(scoped_backend, initial)[0]
    slow = replace(initial, operation_id="slow", product_parents={first["filename"]: first["current"]})
    fast = replace(initial, operation_id="fast")
    writer.commit(fast)
    current = scope_history(scoped_backend, initial)[0]["current"]
    writer.commit(slow)
    assert scope_history(scoped_backend, initial)[0]["current"] == current
    writer.commit(extraction("later-text", "Changed evidence"))
    assert writer.commit(initial).replayed
    assert scope_history(scoped_backend, initial)[0]["current"] == current
    assert initial.commit_id != replace(initial, scope=ReadScope("folder", "root")).commit_id


def test_sidecar_partial_scope_products_resume_without_duplicate_history(scoped_backend, monkeypatch):
    writer, reader = scoped_backend
    if not hasattr(reader, "root"):
        pytest.skip("Sidecar step recovery; PostgreSQL rollback is tested separately")
    from osii.domain.artifacts import products
    command = scope_command(scoped_backend)
    publish = products.publish_product
    def interrupted(root, path, data, **kwargs):
        if data["artifact_type"] == "wiki_markdown":
            raise OSError("Interrupted second scope product")
        return publish(root, path, data, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(products, "publish_product", interrupted)
        with pytest.raises(OSError):
            writer.commit(command)
    assert len(scope_history(scoped_backend, command)) == 1
    writer.commit(command)
    assert all(len(history["revisions"]) == 1 for history in scope_history(scoped_backend, command))


@pytest.mark.parametrize("scope_kind", ["root", "folder", "collection"])
@pytest.mark.parametrize("kind", ["synthesis", "enrichment"])
def test_local_remote_scope_workflows_use_shared_commits(scoped_backend, scope_kind, kind, monkeypatch):
    writer, reader = scoped_backend
    if not hasattr(reader, "root"):
        pytest.skip("Local HTTP adapters belong to the sidecar composition")
    from dataclasses import asdict
    from osii.processors import remote
    from osii.domain.artifacts.products import product_provenance
    from osii.enrichment.common import frozen_scope_inputs
    command = scope_command(scoped_backend, scope_kind, kind)
    scope = writer._scope(command)
    texts = [{"file_id": row.file_id, "text": reader.get_representation(row.file_id).text[:12],
        "source_sha256": row.text_sha256, "extraction_id": row.representation_id,
        "path": "source.pdf"} for row in command.input_revision.inputs]
    descriptor = {**command.expected_processor.model_dump(mode="json"), "base_url": "http://scope-tool.test"}
    if kind == "synthesis":
        processor = remote.RemoteSynthesizer(descriptor)
        class Client:
            def synthesize(self, request):
                assert len(request.scope.documents[0].text) == 12
                return command.response.model_copy(update={"request_id": request.request_id})
        processor._client = Client()
        call = lambda: processor.synthesize_scope(osii_store=reader.root, scope=scope)
    else:
        processor = remote.RemoteEnricher(descriptor)
        def request(url, *, payload, **kwargs):
            assert len(payload["scope"]["documents"][0]["text"]) == 12
            return command.response.model_copy(update={"request_id": payload["request_id"]}).model_dump(mode="json")
        monkeypatch.setattr(remote, "_request_json", request)
        call = lambda: processor.enrich(osii_store=reader.root, scope=scope)
    with frozen_scope_inputs(reader.root, scope, texts), product_provenance({
        "run_id": "remote-scope-run", "processing_revision": asdict(command.input_revision)}):
        result = call()
        assert result["ok"]
        assert call()["ok"]
    histories = scope_history(scoped_backend, command)
    assert len(histories) == (1 if kind == "synthesis" else 2)
    assert all(len(history["revisions"]) == 1 for history in histories)
