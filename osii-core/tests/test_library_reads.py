"""One read contract, exercised against portable files and real PostgreSQL."""
from __future__ import annotations

import json
import os
from pathlib import Path
import uuid

import pytest
import tomli_w

from osii.domain.read.contracts import LibraryReader, ReadScope
from osii.domain.read.sidecar import SidecarLibraryReader

TEXT = "Neutron detector.\nCalibration results."
ORIGIN = {"page": 1, "bbox": [0.1, 0.2, 0.8, 0.4], "confidence": 0.93}
SEGMENTS = [{"id": "seg-000001", "kind": "text", "path": "text.txt",
    "span": {"char_start": 0, "char_end": len(TEXT)}, "source_origin": ORIGIN}]
ARTIFACTS = {
    "entities": {"artifact_type": "entity_list", "title": "Entities", "entities": [{"id": "detector", "name": "detector", "entity_type": "instrument"}]},
    "graph": {"artifact_type": "knowledge_graph", "title": "Graph", "nodes": [], "edges": []},
    "table": {"artifact_type": "table", "title": "Statistics", "columns": [{"key": "words", "label": "Words", "data_type": "integer"}], "rows": [{"words": 4}]},
    "wiki": {"artifact_type": "wiki_markdown", "title": "Wiki", "markdown": "# Detector\n\nCited description.", "citations": [{"file_id": "sha256-a", "page": 1}]},
}
DOCUMENTS = [("sha256-a", "reports/A.txt"), ("sha256-b", "reports/b.txt"),
             ("sha256-c", "reports-other/é.txt")]


def seed_sidecars(root: Path):
    for file_id, path in DOCUMENTS:
        obj = root / "objects" / file_id
        obj.mkdir(parents=True)
        meta = {"file": {"source_relpath": path, "filename": Path(path).name,
                        "mime": "text/plain", "size_bytes": 42}, "hash": {"sha256": file_id[7:]}}
        (obj / "meta.toml").write_text(tomli_w.dumps(meta), encoding="utf-8")
        (obj / "text.txt").write_text(TEXT, encoding="utf-8")
        (obj / "manifest.jsonl").write_text("\n".join(json.dumps(row) for row in SEGMENTS), encoding="utf-8")
        (obj / "provenance.toml").write_text(tomli_w.dumps({"provenance": {"status": "done"}, "extractor": {"name": "test.extractor", "version": "1"}}), encoding="utf-8")
    collection = root / "collections" / "col-test"
    collection.mkdir(parents=True)
    (collection / "collection.toml").write_text(tomli_w.dumps({"collection": {"id": "col-test", "name": "Test"}}), encoding="utf-8")
    (collection / "members.jsonl").write_text(json.dumps({"file_id": "sha256-b"}) + "\n", encoding="utf-8")
    artifacts = root / "objects" / "sha256-a" / "enrichments"
    artifacts.mkdir()
    for name, payload in ARTIFACTS.items():
        (artifacts / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture(params=["sidecar", "sidecar-catalog", "postgres"])
def reader(request, tmp_path) -> LibraryReader:
    if request.param.startswith("sidecar"):
        root = tmp_path / ".osii"
        seed_sidecars(root)
        if request.param == "sidecar-catalog":
            from osii.domain.catalog_db import rebuild_catalog
            rebuild_catalog(root)
        return SidecarLibraryReader(root)
    return request.getfixturevalue("postgres_reader")


@pytest.fixture
def postgres_reader():
    url = os.environ.get("OSII_READ_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set OSII_READ_TEST_DATABASE_URL for the real PostgreSQL read contract")
    from sqlalchemy import create_engine, text
    from osii.domain.read.postgres import PostgresLibraryReader
    # Never replace public or run production migrations. Each test owns only
    # its generated schema, even when pointed at an existing test database.
    schema = "read_contract_" + uuid.uuid4().hex
    admin = create_engine(url.replace("postgresql://", "postgresql+psycopg://", 1))
    with admin.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(admin.url, connect_args={"options": f"-c search_path={schema}"})
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE documents(file_id text PRIMARY KEY, source_relpath text, filename text, media_type text, size_bytes bigint, sha256 text, metadata jsonb, text text, active boolean DEFAULT true)"))
            conn.execute(text("CREATE TABLE extractions(id text PRIMARY KEY, file_id text, response jsonb, created_at timestamptz DEFAULT now())"))
            conn.execute(text("CREATE TABLE artifacts(id text PRIMARY KEY, file_id text, kind text, payload jsonb)"))
            conn.execute(text("CREATE TABLE collections(id text PRIMARY KEY, members jsonb, visibility text, owner_id text)"))
            for file_id, path in DOCUMENTS:
                metadata = {"primary_extraction_id": "extract-" + file_id,
                    "segments": SEGMENTS}
                conn.execute(text("INSERT INTO documents VALUES (:id,:path,:name,'text/plain',42,:sha,CAST(:meta AS jsonb),:text,true)"),
                    {"id": file_id, "path": path, "name": Path(path).name, "sha": file_id[7:], "meta": json.dumps(metadata), "text": TEXT})
                response = {"processor": {"name": "test.extractor", "version": "1"},
                    "segments": [{"id": "seg-000001", "text": TEXT, "source_origin": ORIGIN}]}
                conn.execute(text("INSERT INTO extractions(id,file_id,response) VALUES (:id,:file_id,CAST(:response AS jsonb))"),
                    {"id": "extract-" + file_id, "file_id": file_id, "response": json.dumps(response)})
            conn.execute(text("INSERT INTO collections VALUES ('col-test','[\"sha256-b\"]','shared',null)"))
            conn.execute(text("INSERT INTO collections VALUES ('private-test','[\"sha256-a\"]','private','owner')"))
            for name, payload in ARTIFACTS.items():
                conn.execute(text("INSERT INTO artifacts VALUES (:id,'sha256-a',:kind,CAST(:payload AS jsonb))"),
                    {"id": name, "kind": payload["artifact_type"], "payload": json.dumps({
                        "id": name, "kind": payload["artifact_type"], "media_type": "application/json", "data": payload})})
        yield PostgresLibraryReader(engine)
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


def test_scoped_cursor_pages_keep_total_and_never_duplicate(reader):
    page = reader.list_documents(limit=1)
    items = list(page.items)
    while page.next_cursor:
        page = reader.list_documents(limit=1, cursor=page.next_cursor)
        assert page.total == 3
        items.extend(page.items)
    assert [(row.file_id, row.source_relpath) for row in items] == sorted(DOCUMENTS, key=lambda item: (item[1], item[0]))
    assert [row.file_id for row in reader.list_documents(ReadScope("folder", "reports")).items] == ["sha256-a", "sha256-b"]
    assert [row.file_id for row in reader.list_documents(ReadScope("collection", "col-test")).items] == ["sha256-b"]
    assert [row.file_id for row in reader.list_documents(ReadScope("object", "sha256-a")).items] == ["sha256-a"]
    assert reader.list_documents(ReadScope("collection", "missing")).total == 0
    assert reader.list_documents(ReadScope("folder", "Reports")).total == 0


def test_missing_reads_and_empty_scopes(reader):
    assert reader.get_document("missing") is None
    assert reader.get_representation("missing") is None
    assert reader.get_representation("sha256-a", "missing") is None
    assert reader.get_artifact("missing", "missing") is None
    assert reader.get_artifact("sha256-b", "missing") is None
    assert reader.list_artifacts("missing").items == ()
    assert reader.list_documents(ReadScope("folder", "missing")).items == ()


def test_representation_preserves_exact_text_offsets_geometry_and_provenance(reader):
    doc = reader.get_document("sha256-a")
    assert (doc.filename, doc.media_type, doc.size_bytes, doc.sha256) == ("A.txt", "text/plain", 42, "a")
    record = reader.get_representation(doc.file_id)
    assert record.text == TEXT
    segment = record.segments[0]
    assert segment.source_origin == ORIGIN
    assert segment.text == TEXT
    assert record.text[segment.char_start:segment.char_end] == TEXT
    assert record.provenance["extractor"]["name"] == "test.extractor"
    assert reader.get_representation(doc.file_id, record.representation_id) == record


def test_standard_artifacts_paginate_and_read_without_processor_specific_code(reader):
    page = reader.list_artifacts("sha256-a", limit=1)
    items = list(page.items)
    while page.next_cursor:
        page = reader.list_artifacts("sha256-a", limit=1, cursor=page.next_cursor)
        assert page.total == 4
        items.extend(page.items)
    assert {row.kind for row in items} == {value["artifact_type"] for value in ARTIFACTS.values()}
    for artifact in items:
        result = reader.get_artifact("sha256-a", artifact.artifact_id)
        assert result.artifact == artifact
        assert json.loads(result.data) in ARTIFACTS.values()
        from pydantic import TypeAdapter
        from osii.processor_sdk.models import StandardArtifactData
        TypeAdapter(StandardArtifactData).validate_json(result.data)
        with pytest.raises(ValueError, match="byte limit"):
            reader.get_artifact("sha256-a", artifact.artifact_id, max_bytes=1)


def test_invalid_and_cross_scope_cursors_are_rejected(reader):
    for value in ("nonsense", "", "!", "a" * 17000):
        with pytest.raises(ValueError, match="cursor"):
            reader.list_documents(cursor=value)
    cursor = reader.list_documents(limit=1).next_cursor
    with pytest.raises(ValueError, match="cursor"):
        reader.list_documents(ReadScope("folder", "reports"), cursor=cursor)
    with pytest.raises(ValueError, match="cursor"):
        reader.list_artifacts("sha256-a", cursor=cursor)
    for limit in (0, -1, 501, True):
        with pytest.raises(ValueError):
            reader.list_documents(limit=limit)
        with pytest.raises(ValueError):
            reader.list_artifacts("sha256-a", limit=limit)


def test_binary_artifact_content_has_the_same_contract(reader):
    content = b"\x00\x01\xffbinary"
    if isinstance(reader, SidecarLibraryReader):
        path = reader.root / "objects/sha256-a/artifacts/region.bin"
        path.parent.mkdir()
        path.write_bytes(content)
        artifact_id = "artifacts/region.bin"
    else:
        import base64
        from sqlalchemy import text
        artifact_id = "region"
        payload = {"id": "region", "kind": "image", "media_type": "application/octet-stream",
                   "data_base64": base64.b64encode(content).decode()}
        with reader.engine.begin() as conn:
            conn.execute(text("INSERT INTO artifacts VALUES ('region','sha256-a','image',CAST(:body AS jsonb))"),
                         {"body": json.dumps(payload)})
    result = reader.get_artifact("sha256-a", artifact_id)
    assert result.data == content
    assert result.artifact.media_type == "application/octet-stream"
    with pytest.raises(ValueError, match="byte limit"):
        reader.get_artifact("sha256-a", artifact_id, max_bytes=2)


def test_sidecar_reads_do_not_create_or_archive_anything(tmp_path):
    root = tmp_path / ".osii"
    reader = SidecarLibraryReader(root)
    assert reader.get_document("missing") is None
    assert reader.get_representation("missing") is None
    assert reader.list_documents().total == 0
    assert reader.list_artifacts("missing").total == 0
    assert not root.exists()
    seed_sidecars(root)
    before = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    reader.get_document("sha256-a")
    reader.get_representation("sha256-a")
    reader.list_documents()
    reader.list_artifacts("sha256-a")
    assert before == {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    assert not (root / "objects/sha256-a/extractions").exists()
    assert not (root / "state").exists()


def test_sidecar_listing_does_not_publish_an_uncommitted_object(tmp_path):
    seed_sidecars(tmp_path)
    pending = tmp_path / "objects/sha256-pending"
    pending.mkdir()
    pending.joinpath("meta.toml").write_text(tomli_w.dumps({"file": {
        "source_relpath": "pending.txt", "filename": "pending.txt"}}))
    assert SidecarLibraryReader(tmp_path).list_documents().total == 3


def test_sidecar_rejects_path_escape_and_keeps_segment_edits(tmp_path):
    seed_sidecars(tmp_path)
    reader = SidecarLibraryReader(tmp_path)
    for file_id in ("../secret", "/secret", "..", "a\\b"):
        with pytest.raises(ValueError):
            reader.get_document(file_id)
    with pytest.raises(ValueError):
        reader.get_artifact("sha256-a", "../sha256-b/meta.toml")
    edited = tmp_path / "objects/sha256-a/edited_text.json"
    edited.write_text(json.dumps({"segments": [{"id": "seg-000001", "text": "Corrected detector."}]}))
    result = reader.get_representation("sha256-a")
    assert result.kind == "edited_text" and result.text == "Corrected detector."
    assert result.segments == ()  # Original geometry cannot describe new text.


def test_private_collection_visibility_is_bound_to_the_owner(postgres_reader):
    reader = postgres_reader
    assert reader.list_documents(ReadScope("collection", "private-test")).total == 0
    from osii.domain.read.postgres import PostgresLibraryReader
    owner = PostgresLibraryReader(reader.engine, actor_id="owner")
    assert owner.list_documents(ReadScope("collection", "private-test")).items[0].file_id == "sha256-a"


def test_historical_sidecar_representation_does_not_change_the_primary(tmp_path):
    seed_sidecars(tmp_path)
    obj = tmp_path / "objects/sha256-a"
    alternate = obj / "extractions" / "alternate"
    alternate.mkdir(parents=True)
    (alternate / "text.txt").write_text("Different OCR.")
    (alternate / "manifest.jsonl").write_text(json.dumps({"id": "alternate-segment", "kind": "text",
        "span": {"char_start": 0, "char_end": 14}, "source_origin": ORIGIN}))
    (obj / "extractions/index.json").write_text(json.dumps({"primary_id": None, "variants": [{"id": "alternate"}]}))
    reader = SidecarLibraryReader(tmp_path)
    assert reader.get_representation("sha256-a", "alternate").text == "Different OCR."
    assert reader.get_representation("sha256-a").text == TEXT


def test_historical_postgres_representation_and_inactive_records(postgres_reader):
    from sqlalchemy import text
    reader = postgres_reader
    response = {"processor": {"name": "other.extractor"}, "segments": [
        {"id": "one", "text": "Old.", "source_origin": ORIGIN},
        {"id": "two", "text": "OCR.", "source_origin": {"page": 2}}]}
    with reader.engine.begin() as conn:
        conn.execute(text("INSERT INTO extractions(id,file_id,response) VALUES ('old','sha256-a',CAST(:body AS jsonb))"), {"body": json.dumps(response)})
    old = reader.get_representation("sha256-a", "old")
    assert old.text == "Old.\nOCR."
    assert old.segments[1].char_start == 5
    assert old.segments[0].source_origin == ORIGIN
    assert reader.get_representation("sha256-a").text == TEXT
    with reader.engine.begin() as conn:
        conn.execute(text("UPDATE documents SET active=false WHERE file_id='sha256-a'"))
    assert reader.get_document("sha256-a") is None
    assert reader.get_representation("sha256-a") is None
    assert reader.list_artifacts("sha256-a").total == 0
    assert reader.get_artifact("sha256-a", "table") is None
