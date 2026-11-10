"""The same authoring/collection contract on sidecars and real PostgreSQL."""
from dataclasses import replace
import json

import pytest

from test_library_reads import postgres_reader
from test_processing_commits import backend, scoped_backend, scope_command, scope_history, FILE_ID, TEXT
from osii.domain.read.contracts import ReadScope
from osii.domain.storage.authoring import AuthoringConflict, ProductRef


@pytest.fixture
def stores(scoped_backend):
    processing, reader = scoped_backend
    if hasattr(reader, "root"):
        from osii.domain.storage.sidecar_authoring import SidecarProductAuthoring, SidecarCollectionStore
        return SidecarProductAuthoring(reader.root), SidecarCollectionStore(reader.root), processing, reader
    from sqlalchemy import text
    from osii.domain.storage.postgres_authoring import PostgresProductAuthoring, PostgresCollectionStore
    with reader.engine.begin() as conn:
        conn.execute(text("ALTER TABLE collections ADD COLUMN name text NOT NULL DEFAULT ''"))
        conn.execute(text("ALTER TABLE collections ADD COLUMN description text NOT NULL DEFAULT ''"))
        conn.execute(text("UPDATE collections SET name=id"))
    return PostgresProductAuthoring(reader.engine), PostgresCollectionStore(reader.engine), processing, reader


def seed_product(stores, scope_kind="root", artifact_type="wiki_markdown"):
    author, collections, writer, reader = stores
    command = scope_command((writer, reader), scope_kind)
    writer.commit(command)
    history = next(row for row in scope_history((writer, reader), command) if row["data"]["artifact_type"] == artifact_type)
    return ProductRef(command.scope, history["filename"])


@pytest.mark.parametrize("scope_kind", ["root", "folder", "collection"])
def test_save_is_draft_activation_is_revisioned_and_keeps_grounding(stores, scope_kind):
    author, collections, writer, reader = stores
    ref = seed_product(stores, scope_kind)
    original = author.history(ref)
    before = reader.get_representation(FILE_ID)
    data = {**original.active.data, "markdown": "Human-reviewed description."}
    draft = author.save(ref, data, expected_revision=original.active_revision)
    history = author.history(ref)
    assert history.active_revision == original.active_revision
    assert len(history.revisions) == 2
    assert draft.parent_id == original.active_revision and draft.grounding_needs_review
    assert draft.data["citations"] == original.active.data["citations"]
    assert draft.provenance == original.active.provenance
    chosen = author.activate(ref, draft.revision_id, expected_revision=original.active_revision)
    assert chosen.revision_id != draft.revision_id
    assert chosen.provenance["activated_revision"] == draft.revision_id
    assert chosen.parent_id == original.active_revision
    assert author.history(ref).active.data["markdown"] == data["markdown"]
    assert len(author.history(ref).revisions) == 3
    assert reader.get_representation(FILE_ID) == before
    assert before.text == TEXT
    # A stale activation neither adds a revision nor loses the chosen edit.
    with pytest.raises(AuthoringConflict):
        author.activate(ref, original.active_revision, expected_revision=original.active_revision)
    assert len(author.history(ref).revisions) == 3
    writer.commit(replace(scope_command((writer, reader), scope_kind), operation_id="new-generation"))
    assert author.history(ref).active_revision == chosen.revision_id


def test_invalid_edits_and_foreign_activation_leave_history_unchanged(stores):
    author = stores[0]
    ref = seed_product(stores)
    original = author.history(ref)
    for data in ({"artifact_type": "table"}, {**original.active.data, "citations": [{"char_start": -1}]},
                 {**original.active.data, "bad": float("nan")}):
        with pytest.raises(ValueError):
            author.save(ref, data, expected_revision=original.active_revision)
    table = seed_product(stores, "folder", "table")
    foreign = author.history(table).active_revision
    with pytest.raises(KeyError):
        author.activate(ref, foreign, expected_revision=original.active_revision)
    assert author.history(ref) == original


def test_table_edit_uses_typed_format_and_preserves_original_revision(stores):
    author = stores[0]
    ref = seed_product(stores, artifact_type="table")
    previous = author.history(ref)
    revision = author.save(ref, {**previous.active.data, "rows": [{"words": 17}]},
        expected_revision=previous.active_revision, activate=True)
    assert author.history(ref).active_revision == revision.revision_id
    assert author.history(ref).revisions[0] == previous.revisions[0]


def test_authoring_failure_cannot_publish_half_a_revision(stores, monkeypatch):
    author, collections, writer, reader = stores
    ref = seed_product(stores)
    previous = author.history(ref)
    if hasattr(reader, "root"):
        from osii.domain.artifacts import products
        original = products.atomic_write_text
        def fail(path, content):
            if path.name == "manifest.json":
                raise OSError("Simulated failure before commit")
            return original(path, content)
        monkeypatch.setattr(products, "atomic_write_text", fail)
        error = OSError
    else:
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError
        with reader.engine.begin() as conn:
            conn.execute(text("ALTER TABLE scope_revisions ADD CONSTRAINT reject_human CHECK (origin<>'human')"))
        error = IntegrityError
    with pytest.raises(error):
        author.save(ref, {**previous.active.data, "markdown": "Interrupted"},
            expected_revision=previous.active_revision, activate=True)
    assert author.history(ref) == previous


def test_collection_commands_preserve_metadata_and_detect_lost_updates(stores):
    author, collections, writer, reader = stores
    created = collections.create("My collection", description="Original description", collection_id="col-authored")
    assert created.collection_id == "col-authored" and created.member_ids == ()
    updated = collections.update(created.collection_id, name="Reviewed name", expected_version=created.version)
    assert updated.name == "Reviewed name" and updated.description == created.description
    assert updated.metadata.keys() == created.metadata.keys()
    members = collections.replace_members(created.collection_id, [FILE_ID, FILE_ID], expected_version=updated.version)
    assert members.member_ids == (FILE_ID,)
    with pytest.raises(AuthoringConflict):
        collections.update(created.collection_id, description="Lost update", expected_version=updated.version)
    assert collections.get(created.collection_id) == members
    empty = collections.replace_members(created.collection_id, [], expected_version=members.version)
    assert empty.member_ids == ()
    assert reader.get_representation(FILE_ID).text == TEXT
    assert any(row.collection_id == empty.collection_id for row in collections.list())
    with pytest.raises(AuthoringConflict):
        collections.create("Different name", collection_id=created.collection_id)


def test_collection_reference_validation_and_missing_records(stores):
    collections = stores[1]
    assert collections.get("missing") is None
    with pytest.raises(KeyError):
        collections.update("missing", name="Changed", expected_version="unknown")
    with pytest.raises(ValueError):
        collections.create("", collection_id="blank")
    with pytest.raises(ValueError):
        collections.get("../escape")
    record = collections.create("Valid", collection_id="col-valid")
    with pytest.raises(ValueError):
        collections.replace_members(record.collection_id, "not-a-list", expected_version=record.version)
    assert collections.get(record.collection_id) == record


def test_collection_membership_changes_invalidate_processing_not_human_history(stores):
    from osii.domain.storage.commits import CommitConflict
    author, collections, writer, reader = stores
    ref = seed_product(stores, "collection")
    current = author.history(ref)
    author.save(ref, {**current.active.data, "markdown": "Preserve this human edit"},
        expected_revision=current.active_revision, activate=True)
    pending = replace(scope_command((writer, reader), "collection"), operation_id="waiting-on-members")
    record = collections.get("col-aggregate")
    collections.replace_members(record.collection_id, [], expected_version=record.version)
    with pytest.raises(CommitConflict, match="membership changed"):
        writer.commit(pending)
    assert author.history(ref).active.data["markdown"] == "Preserve this human edit"


def test_sidecar_metadata_and_member_annotations_survive_updates(stores):
    author, collections, writer, reader = stores
    if not hasattr(reader, "root"):
        pytest.skip("Portable sidecar annotations are retained in their canonical files")
    from osii.domain.scopes.collections import _write_collection, _read_collection, _write_members, _read_members
    created = collections.create("Annotations", collection_id="col-annotations")
    path = reader.root / "collections/col-annotations/collection.toml"
    raw = _read_collection(path)
    _write_collection(reader.root, {**raw, "color": "red", "custom_note": "Retain me"})
    _write_members(reader.root, created.collection_id, [{"file_id": FILE_ID, "created_utc": "original-time", "note": "Keep this too"}])
    record = collections.get(created.collection_id)
    changed = collections.update(record.collection_id, name="Renamed", expected_version=record.version)
    assert changed.metadata["custom_note"] == "Retain me" and changed.metadata["color"] == "red"
    collections.replace_members(record.collection_id, [FILE_ID, "another-id"], expected_version=changed.version)
    assert next(row for row in _read_members(reader.root, record.collection_id) if row["file_id"] == FILE_ID)["note"] == "Keep this too"


def test_sidecar_imports_old_product_history_without_rewriting_it(stores):
    author, collections, writer, reader = stores
    if not hasattr(reader, "root"):
        pytest.skip("Legacy files are specific to sidecar compatibility")
    from osii.domain.artifacts.products import product_path
    ref = ProductRef(ReadScope("root", "root"), "legacy/wiki.json")
    path = product_path(reader.root, ref.legacy_scope(), ref.filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"artifact_type": "wiki_markdown", "title": "Old wiki", "markdown": "Legacy human text", "citations": [{"file_id": FILE_ID}]}
    path.write_text(json.dumps(payload), encoding="utf-8")
    before = path.read_bytes()
    history = author.history(ref)
    assert path.read_bytes() == before
    assert history.active.data == payload
    author.save(ref, {**payload, "markdown": "New draft"}, expected_revision=history.active_revision)
    assert path.read_bytes() == before
    assert author.history(ref).revisions[0] == history.revisions[0]


def test_postgres_collection_visibility_is_not_an_authentication_bypass(stores):
    reader = stores[3]
    if not hasattr(reader, "engine"):
        pytest.skip("OSII-local has no hosted accounts or visibility rules")
    from osii.domain.storage.postgres_authoring import PostgresCollectionStore
    owner = PostgresCollectionStore(reader.engine, actor_id="owner", visibility="private")
    other = PostgresCollectionStore(reader.engine, actor_id="other")
    record = owner.create("Private", collection_id="col-private")
    assert other.get(record.collection_id) is None
    with pytest.raises(KeyError):
        other.replace_members(record.collection_id, [], expected_version=record.version)
