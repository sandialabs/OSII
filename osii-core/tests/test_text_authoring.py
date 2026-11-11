"""Preferred text has the same edit contract on sidecars and PostgreSQL."""

from __future__ import annotations

import pytest

from test_library_reads import postgres_reader  # noqa: F401 -- shared fixture
from test_processing_commits import backend as backend, extraction, FILE_ID
from osii.domain.storage.authoring import AuthoringConflict


def test_text_edit_clear_and_stale_compare_and_swap(backend):
    writer, reader = backend
    writer.commit(extraction())
    if hasattr(reader, "root"):
        from osii.domain.storage.text_authoring import SidecarTextAuthoring

        editor = SidecarTextAuthoring(reader.root)
    else:
        from osii.domain.storage.text_authoring import PostgresTextAuthoring

        editor = PostgresTextAuthoring(reader.engine)
    canonical = reader.get_representation(FILE_ID, "canonical")
    first = editor.save(
        FILE_ID,
        [
            {
                "id": canonical.segments[0].segment_id,
                "text": "Human reviewed detector calibration.",
            }
        ],
        expected_revision=None,
    )
    assert first.text == "Human reviewed detector calibration."
    assert reader.get_representation(FILE_ID).text == first.text
    assert not reader.get_representation(
        FILE_ID
    ).segments  # Do not invent geometry for edits.
    assert reader.get_representation(FILE_ID, "canonical") == canonical
    with pytest.raises(AuthoringConflict):
        editor.save(FILE_ID, [], expected_revision=None)
    with pytest.raises(ValueError):
        editor.save(
            FILE_ID, [{"id": "unknown", "text": "No"}], expected_revision=first.revision
        )
    editor.save(FILE_ID, None, expected_revision=first.revision)
    assert reader.get_representation(FILE_ID).text == canonical.text
    assert editor.get(FILE_ID).revision is None


def test_new_primary_extraction_preserves_human_history(backend):
    writer, reader = backend
    writer.commit(extraction())
    if hasattr(reader, "root"):
        from osii.domain.storage.text_authoring import SidecarTextAuthoring

        editor = SidecarTextAuthoring(reader.root)
    else:
        from osii.domain.storage.text_authoring import PostgresTextAuthoring

        editor = PostgresTextAuthoring(reader.engine)
    segment = reader.get_representation(FILE_ID, "canonical").segments[0].segment_id
    changed = editor.save(
        FILE_ID, [{"id": segment, "text": "Curated text"}], expected_revision=None
    )
    writer.commit(extraction("replacement", "Better grounded extraction"))
    assert (
        reader.get_representation(FILE_ID, "canonical").text
        == "Better grounded extraction"
    )
    if hasattr(reader, "root"):
        import json

        history = json.loads(
            (reader.root / "objects" / FILE_ID / "edited_text.history.json").read_text()
        )
    else:
        from sqlalchemy import text

        with reader.engine.connect() as conn:
            history = conn.execute(
                text(
                    "SELECT metadata->'edited_text_history' FROM documents WHERE file_id=:id"
                ),
                {"id": FILE_ID},
            ).scalar()
    assert any(
        row["id"] == changed.revision and row["text"] == "Curated text"
        for row in history
    )
