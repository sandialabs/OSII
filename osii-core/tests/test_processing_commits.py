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
    ProcessingCommit, SourceRecord, text_digest)
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
