"""Shared SQL contract: real PostgreSQL, isolated schema, no production migrations."""

import json
import os
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytest.importorskip("sqlglot")
from osii.api.database_routes import create_database_router
from osii.domain.storage.database_query import (
    DatabaseExplorer,
    QueryBusy,
    QueryRejected,
    QueryUnavailable,
    compile_query,
)

RELATIONS = {
    "documents": [{"name": "file_id"}, {"name": "filename"}, {"name": "metadata"}]
}


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM documents",
        "UPDATE documents SET filename='x'",
        "CREATE TABLE x(id int)",
        "SELECT 1; SELECT 2",
        "COPY documents TO '/tmp/leak'",
        "SET search_path=public",
        "EXPLAIN ANALYZE SELECT * FROM documents",
        "SELECT * INTO stolen FROM documents",
        "WITH x AS (DELETE FROM documents RETURNING *) SELECT * FROM x",
        "WITH RECURSIVE x AS (SELECT 1 UNION ALL SELECT * FROM x) SELECT * FROM x",
        "SELECT * FROM documents FOR UPDATE",
        "SELECT * FROM documents FOR SHARE",
        "SELECT pg_sleep(10)",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT lo_import('/etc/passwd')",
        "SELECT set_config('search_path','public',true)",
        "SELECT nextval('seq')",
        "SELECT public.lower(filename) FROM documents",
        "SELECT * FROM pg_authid",
        "SELECT * FROM users",
        "SELECT * FROM sessions",
        "SELECT * FROM settings",
        "SELECT * FROM public.documents",
        "SELECT * FROM information_schema.tables",
        "SELECT * FROM generate_series(1,1000)",
        "SELECT 'documents'::regclass",
        "SELECT 'x'::public.custom_type",
        "SELECT * FROM documents TABLESAMPLE SYSTEM(1)",
        "SELECT filename COLLATE public.custom FROM documents",
        "SELECT current_user",
        "SELECT * FROM documents UNION SELECT * FROM secrets",
        "SELECT pg_notify('a','b')",
        "SELECT * FROM ((users)) x",
        "SELECT * FROM ((pg_authid)) x",
        "SELECT * FROM (documents JOIN ((pg_authid)) x ON true)",
        "SELECT * FROM (documents JOIN documents b ON true) x",
        "SELECT * FROM ((public.documents)) x",
        'WITH "PG_AUTHID" AS (SELECT 1) SELECT * FROM PG_AUTHID',
        'WITH PG_AUTHID AS (SELECT 1) SELECT * FROM "PG_AUTHID"',
    ],
)
def test_rejects_non_library_or_unsafe_sql(sql):
    with pytest.raises(QueryRejected):
        compile_query(sql, "test_schema", RELATIONS)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM documents",
        "SELECT filename FROM documents WHERE filename ILIKE '%data%'",
        "WITH x AS (SELECT filename FROM documents) SELECT * FROM x",
        "SELECT count(*) FROM documents a JOIN documents b ON a.file_id=b.file_id",
        "SELECT metadata ->> 'title' FROM documents",
        "SELECT 'a; DELETE FROM users' AS literal",
        "SELECT 1 UNION ALL SELECT 2",
        "SELECT filename, count(*) FROM documents GROUP BY filename HAVING count(*)>0",
        "SELECT FILENAME FROM DOCUMENTS",
        'WITH "X" AS (SELECT filename FROM documents) SELECT * FROM "X"',
    ],
)
def test_compiles_supported_queries(sql):
    compiled = compile_query(sql, "test_schema", RELATIONS)
    if "FROM documents" in sql:
        assert '"test_schema"."documents"' in compiled
    assert "DELETE FROM users" not in compiled or "'a; DELETE FROM users'" in compiled


def test_parser_warnings_never_include_submitted_text(caplog):
    with pytest.raises(QueryRejected):
        compile_query("VACUUM private-sensitive-name", "test_schema", RELATIONS)
    assert "private-sensitive-name" not in caplog.text


def test_connection_failure_is_sanitized():
    from unittest.mock import Mock

    from sqlalchemy.exc import OperationalError

    engine = Mock()
    engine.dialect.name = "postgresql"
    engine.connect.side_effect = OperationalError(
        "secret-sql", {}, RuntimeError("secret-password")
    )
    with pytest.raises(QueryUnavailable) as caught:
        DatabaseExplorer(engine).schema()
    assert "secret" not in str(caught.value)


@pytest.fixture
def explorer():
    url = os.environ.get("OSII_READ_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set OSII_READ_TEST_DATABASE_URL for real PostgreSQL query tests")
    from sqlalchemy import create_engine, text

    admin = create_engine(url.replace("postgresql://", "postgresql+psycopg://", 1))
    schema = "query_contract_" + uuid.uuid4().hex
    with admin.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(
        admin.url, connect_args={"options": f"-csearch_path={schema}"}
    )
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE documents(file_id text, filename text, source_relpath text, metadata jsonb, text text, password_hash text)"
                )
            )
            conn.execute(text("CREATE TABLE users(password_hash text)"))
            conn.execute(text("INSERT INTO users VALUES ('never-visible-secret')"))
            conn.execute(text("CREATE TABLE jobs(id text, status text, payload jsonb)"))
            conn.execute(
                text(
                    "INSERT INTO jobs VALUES ('job','queued','{\"credential\":\"never-visible-secret\"}')"
                )
            )
            conn.execute(
                text("CREATE VIEW artifacts AS SELECT password_hash FROM users")
            )
            conn.execute(
                text(
                    "INSERT INTO documents VALUES ('id1','dataset.txt','dataset.txt','{\"title\":\"Neutrons\"}','Grounded text','never-visible-secret')"
                )
            )
            # Even functions with familiar names must resolve only in pg_catalog.
            conn.execute(
                text(
                    "CREATE FUNCTION lower(text) RETURNS text LANGUAGE sql AS $$ SELECT password_hash FROM users LIMIT 1 $$"
                )
            )
        yield DatabaseExplorer(engine)
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


def test_projection_and_schema_exclude_secrets_and_views(explorer):
    schema = explorer.schema()
    assert {t["name"] for t in schema["tables"]} == {"documents", "jobs"}
    assert "password_hash" not in json.dumps(schema) and "payload" not in json.dumps(
        schema
    )
    result = explorer.query("SELECT * FROM documents")
    assert "never-visible-secret" not in json.dumps(result)
    assert result["rows"][0]["c0"] == "id1"
    assert explorer.query("SELECT lower(filename) FROM documents")["rows"] == [
        {"c0": "dataset.txt"}
    ]
    for sql in (
        "SELECT * FROM users",
        "SELECT * FROM artifacts",
        "SELECT rolpassword FROM ((pg_authid)) x",
        'WITH "PG_AUTHID" AS (SELECT 1) SELECT * FROM PG_AUTHID',
    ):
        with pytest.raises(QueryRejected):
            explorer.query(sql)
    with pytest.raises(QueryUnavailable, match="Unknown column"):
        explorer.query("SELECT password_hash FROM documents")


def test_queries_ctes_json_percent_duplicate_labels_and_precision(explorer):
    result = explorer.query(
        "WITH x AS (SELECT filename,metadata FROM documents WHERE filename ILIKE '%data%') SELECT filename AS name,metadata->>'title' AS name FROM x"
    )
    assert result["rows"] == [{"c0": "dataset.txt", "c1": "Neutrons"}]
    assert [c["label"] for c in result["columns"]] == ["name", "name"]
    assert explorer.query(
        "SELECT 9007199254740993::bigint,1.1234567890123456789::numeric,NULL"
    )["rows"] == [{"c0": "9007199254740993", "c1": "1.1234567890123456789", "c2": None}]
    assert explorer.query(
        "SELECT count(*) FROM documents a JOIN documents b ON a.file_id=b.file_id"
    )["rows"] == [{"c0": 1}]


@pytest.mark.parametrize("autocommit", [False, True])
def test_transaction_blocks_writes_even_if_parser_is_bypassed(
    explorer, monkeypatch, autocommit
):
    if autocommit:
        explorer = DatabaseExplorer(
            explorer.engine.execution_options(isolation_level="AUTOCOMMIT")
        )
    monkeypatch.setattr(
        "osii.domain.storage.database_query.compile_query",
        lambda *args: "DELETE FROM documents RETURNING filename",
    )
    # Bypass only the description SELECT to reach the database write guard.
    from sqlalchemy import text
    from sqlalchemy.engine import Connection

    with explorer.engine.connect() as conn:
        schema = conn.execute(text("SELECT current_schema()")).scalar_one()
    original = Connection.exec_driver_sql

    def bypass_description(self, sql, *args, **kwargs):
        if "__osii_description" in sql:
            return original(self, f'SELECT filename FROM "{schema}".documents LIMIT 0')
        return original(self, f'DELETE FROM "{schema}".documents RETURNING filename')

    monkeypatch.setattr(Connection, "exec_driver_sql", bypass_description)
    with pytest.raises(QueryUnavailable, match="write attempt"):
        explorer.query("ignored")
    from sqlalchemy import text

    with explorer.engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM documents")).scalar_one() == 1
        assert conn.execute(text("SHOW transaction_read_only")).scalar_one() == "off"


def test_bounds_errors_and_pool_recovery(explorer, monkeypatch):
    from sqlalchemy import text

    with explorer.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO documents(file_id,filename,text) SELECT id::text,'é',repeat('x',5000) FROM generate_series(2,250) id"
            )
        )
    result = explorer.query("SELECT text FROM documents ORDER BY file_id", limit=2)
    assert (
        result["row_count"] == 2
        and result["limited"]
        and result["truncated_cells"] >= 1
    )
    assert "truncated" in json.dumps(result)
    for limit in (0, 201, True):
        with pytest.raises(QueryRejected):
            explorer.query("SELECT 1", limit=limit)
    with pytest.raises(QueryRejected):
        explorer.query("SELECT " + ",".join("1" for _ in range(33)))
    with pytest.raises(QueryUnavailable, match="Division by zero"):
        explorer.query("SELECT 1/0")
    monkeypatch.setattr("osii.domain.storage.database_query.TIMEOUT_MS", 10)
    with pytest.raises(QueryUnavailable, match="timed out"):
        explorer.query(
            "SELECT count(*) FROM documents a CROSS JOIN documents b CROSS JOIN documents c CROSS JOIN documents d"
        )
    assert explorer.query("SELECT 1")["rows"] == [{"c0": 1}]
    explorer._admission.acquire()
    try:
        with pytest.raises(QueryBusy):
            explorer.query("SELECT 1")
    finally:
        explorer._admission.release()


def test_local_composition_is_unavailable_for_sidecars_and_requires_explicit_auth_callback():
    app = FastAPI()
    app.include_router(
        create_database_router(lambda request: None, authorize=lambda: None)
    )
    client = TestClient(app)
    assert client.get("/api/admin/database/schema").json()["available"] is False
    assert (
        client.post("/api/admin/database/query", json={"sql": "SELECT 1"}).status_code
        == 409
    )
    assert (
        client.post(
            "/api/admin/database/query", json={"sql": "SELECT 1", "limit": True}
        ).status_code
        == 422
    )
    with pytest.raises(TypeError):
        create_database_router(lambda request: None)


def test_large_result_byte_cap_and_json_precision(explorer):
    from sqlalchemy import text

    with explorer.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO documents(file_id,text) SELECT id::text,repeat('😀',5000) FROM generate_series(2,250) id"
            )
        )
    result = explorer.query(
        "SELECT " + ",".join("text" for _ in range(32)) + " FROM documents", limit=200
    )
    assert result["limited"] and 0 < result["row_count"] < 200
    assert len(json.dumps(result["rows"], ensure_ascii=False).encode()) <= 1_001_000
    assert explorer.query("SELECT '{\"large\":9007199254740993}'::jsonb")["rows"] == [
        {"c0": {"large": "9007199254740993"}}
    ]


def test_lock_timeout_and_recovery(explorer):
    from sqlalchemy import text

    with explorer.engine.connect() as blocker, blocker.begin():
        blocker.execute(text("LOCK documents IN ACCESS EXCLUSIVE MODE"))
        with pytest.raises(QueryUnavailable, match="library is busy"):
            explorer.query("SELECT * FROM documents")
    assert explorer.query("SELECT 1")["rows"] == [{"c0": 1}]


def test_router_results_errors_and_audit(explorer):
    events = []
    app = FastAPI()
    app.include_router(
        create_database_router(
            lambda request: explorer,
            authorize=lambda: {"id": "operator"},
            audit=lambda principal, outcome, fingerprint: events.append(
                (principal, outcome, fingerprint)
            ),
        )
    )
    client = TestClient(app)
    assert client.get("/api/admin/database/schema").status_code == 200
    assert (
        client.post(
            "/api/admin/database/query", json={"sql": "SELECT filename FROM documents"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/admin/database/query", json={"sql": "DELETE FROM documents"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/admin/database/query", json={"sql": "SELECT unknown FROM documents"}
        ).status_code
        == 503
    )
    assert (
        len(events) == 3 and events[0][1] == "completed" and events[1][1] == "rejected"
    )
    assert all(len(event[2]) == 64 for event in events)
    assert "SELECT" not in json.dumps(events)
