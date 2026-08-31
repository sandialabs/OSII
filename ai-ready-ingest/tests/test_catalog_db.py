import json
import os
import sqlite3
from unittest.mock import patch

import pytest

import osii.domain.catalog_db as catalog_db
from osii.domain.catalog_db import catalog_path, list_documents, rebuild_catalog, verify_catalog
from osii.domain.scopes.collections import init_collections_db, list_collections
from osii.domain.storage.folders import write_folder_manifest


def test_catalog_rebuild_closes_temporary_descriptor(temp_osii_root):
    with patch("osii.domain.catalog_db.os.close", wraps=os.close) as close:
        rebuild_catalog(temp_osii_root)

    close.assert_called_once()


def test_catalog_rebuild_closes_sqlite_before_atomic_replace(temp_osii_root):
    real_connect = catalog_db._connect_path
    real_replace = os.replace
    tracked_connections = []

    class TrackedConnection:
        def __init__(self, connection):
            self.connection = connection
            self.closed = False

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def close(self):
            self.connection.close()
            self.closed = True

    def tracked_connect(path):
        connection = TrackedConnection(real_connect(path))
        tracked_connections.append(connection)
        return connection

    def assert_closed_then_replace(source, target):
        assert tracked_connections[-1].closed is True
        real_replace(source, target)

    with (
        patch("osii.domain.catalog_db._connect_path", side_effect=tracked_connect),
        patch("osii.domain.catalog_db.os.replace", side_effect=assert_closed_then_replace),
    ):
        rebuild_catalog(temp_osii_root)

    assert tracked_connections


def test_catalog_connection_closes_if_database_setup_fails(tmp_path):
    class FailingConnection:
        closed = False
        row_factory = None

        def execute(self, _statement):
            raise sqlite3.DatabaseError("file is not a database")

        def close(self):
            self.closed = True

    connection = FailingConnection()
    with patch("osii.domain.catalog_db.sqlite3.connect", return_value=connection):
        with pytest.raises(sqlite3.DatabaseError, match="file is not a database"):
            catalog_db._connect_path(tmp_path / "catalog.sqlite3")

    assert connection.closed is True


def test_catalog_rebuild_and_cursor_pagination(temp_osii_root):
    write_folder_manifest(temp_osii_root, "root", "", [{"source_relpath": f"docs/{index:03}.txt", "file_id": f"file-{index:03}"} for index in range(12)], [], None, None)
    result = rebuild_catalog(temp_osii_root)
    assert result["counts"]["documents"] == 12
    first = list_documents(temp_osii_root, limit=5, suffix="txt")
    second = list_documents(temp_osii_root, limit=5, cursor=first["next_cursor"])
    assert first["total"] == 12
    assert {item["file_id"] for item in first["items"]}.isdisjoint(item["file_id"] for item in second["items"])
    assert verify_catalog(temp_osii_root)["ok"] is True


def test_corrupt_catalog_is_quarantined_and_rebuilt(temp_osii_root):
    path = catalog_path(temp_osii_root)
    path.write_bytes(b"not sqlite")
    page = list_documents(temp_osii_root)
    assert page["items"] == []
    assert list(path.parent.glob("catalog.corrupt-*.sqlite3"))


def test_legacy_collection_database_migrates_to_canonical_files(temp_osii_root):
    legacy = temp_osii_root / ".collections" / "collections.sqlite"
    legacy.parent.mkdir(parents=True)
    with sqlite3.connect(legacy) as conn:
        conn.executescript("CREATE TABLE collections(id TEXT PRIMARY KEY,name TEXT,description TEXT,kind TEXT,color TEXT,created_utc TEXT,updated_utc TEXT); CREATE TABLE collection_documents(collection_id TEXT,file_id TEXT,created_utc TEXT);")
        conn.execute("INSERT INTO collections VALUES (?,?,?,?,?,?,?)", ("col-old", "Old", "legacy", "manual", None, "2026-01-01Z", "2026-01-01Z"))
        conn.execute("INSERT INTO collection_documents VALUES (?,?,?)", ("col-old", "file-a", "2026-01-01Z"))
    init_collections_db(temp_osii_root)
    assert (temp_osii_root / "collections" / "col-old" / "collection.toml").exists()
    assert json.loads((temp_osii_root / "collections" / "col-old" / "members.jsonl").read_text())["file_id"] == "file-a"
    assert list_collections(temp_osii_root)[0]["document_count"] == 1
