"""Bounded PostgreSQL library inspection, independent of HTTP and user accounts.

This is not a general database administration console. Only explicit library
projections are queryable; credentials, accounts, settings and job payloads are
never part of the query namespace. Execute generated, validated SQL, not input.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from threading import BoundedSemaphore
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection, Engine

SQL_LIMIT = 16_000
ROW_LIMIT = 200
CELL_LIMIT = 2_048
BYTE_LIMIT = 1_000_000
TIMEOUT_MS = 2_000
COLUMN_LIMIT = 32

# Extend this projection explicitly when a new Core data table is introduced.
# Never add operational secrets, accounts, sessions or provider configuration.
RELATIONS = {
    "documents": "file_id source_relpath active sha256 filename media_type size_bytes text metadata updated_at",
    "extractions": "id file_id sha256 response created_at",
    "chunks": "chunk_id file_id text char_start char_end source_origin embedding embedding_model",
    "artifacts": "id file_id kind payload",
    "scope_products": "id scope_type scope_id filename family method current_revision title artifact_type",
    "scope_revisions": "id product_id parent origin created_at actor_id data provenance",
    "collections": "id name description members owner_id visibility",
    "datasets": "id revision",
    "jobs": "id kind status attempts worker_id lease_until created_at",
    "import_files": "import_id path sha256",
}
NODES = frozenset(
    [
        "select",
        "union",
        "intersect",
        "except",
        "subquery",
        "with",
        "cte",
        "from",
        "table",
        "tablealias",
        "column",
        "identifier",
        "literal",
        "boolean",
        "null",
        "star",
        "alias",
        "join",
        "where",
        "group",
        "having",
        "order",
        "ordered",
        "limit",
        "offset",
        "distinct",
        "paren",
        "eq",
        "neq",
        "gt",
        "gte",
        "lt",
        "lte",
        "and",
        "or",
        "not",
        "is",
        "in",
        "between",
        "like",
        "ilike",
        "escape",
        "add",
        "sub",
        "mul",
        "div",
        "mod",
        "neg",
        "case",
        "if",
        "coalesce",
        "nullif",
        "cast",
        "datatype",
        "datatypeparam",
        "tuple",
        "array",
        "bracket",
        "jsonextract",
        "jsonextractscalar",
        "jsonpath",
        "jsonpathkey",
        "jsonpathroot",
        "jsonpathsubscript",
        "count",
        "sum",
        "avg",
        "min",
        "max",
        "lower",
        "upper",
        "length",
        "substring",
        "trim",
        "concat",
        "abs",
        "round",
        "ceil",
        "floor",
        "exists",
        "anonymous",
        "dpipe",
        "filter",
        "window",
        "windowspec",
        "partition",
    ]
)
FUNCTIONS = frozenset(
    {
        "jsonb_array_length",
        "jsonb_typeof",
        "jsonb_extract_path",
        "jsonb_extract_path_text",
        "to_jsonb",
        "pg_column_size",
    }
)
TYPES = frozenset(
    [
        "TEXT",
        "VARCHAR",
        "CHAR",
        "BOOLEAN",
        "SMALLINT",
        "INT",
        "BIGINT",
        "FLOAT",
        "DOUBLE",
        "DECIMAL",
        "DATE",
        "TIMESTAMP",
        "TIMESTAMPTZ",
        "JSON",
        "JSONB",
    ]
)


class QueryRejected(ValueError):
    pass


class QueryUnavailable(RuntimeError):
    pass


class QueryBusy(RuntimeError):
    pass


def _safe_integer(value: str) -> int | str:
    number = int(value)
    return number if abs(number) <= 9_007_199_254_740_991 else value


def compile_query(sql: str, schema: str, relations: dict[str, list[dict]]) -> str:
    """Parse one SELECT, reject unsupported syntax, and scope every base table."""
    import sqlglot
    from sqlglot import ErrorLevel, exp
    from sqlglot.optimizer.normalize_identifiers import normalize_identifiers
    from sqlglot.optimizer.scope import traverse_scope

    if not isinstance(sql, str) or not sql.strip() or len(sql) > SQL_LIMIT:
        raise QueryRejected("Enter one SELECT query of at most 16,000 characters.")
    try:
        # Some unsupported commands are logged by the parser. A zero context
        # prevents that dependency from including submitted text in warnings.
        statements = sqlglot.parse(
            sql, read="postgres", max_nodes=1_000, error_message_context=0
        )
        if len(statements) != 1 or not isinstance(
            statements[0], (exp.Select, exp.SetOperation)
        ):
            raise QueryRejected("Only one SELECT query is allowed.")
        # Scope analysis must use PostgreSQL's case folding. Otherwise a quoted
        # CTE named "PG_AUTHID" could be mistaken for an unquoted pg_authid read.
        tree = normalize_identifiers(statements[0], dialect="postgres")
        original_tables = {id(table) for table in tree.find_all(exp.Table)}
        resolved_tables = set()
        nodes = list(tree.walk())
        if len(nodes) > 1_000:
            raise QueryRejected("This query is too complex; simplify it.")
        for node in nodes:
            if node.key not in NODES:
                raise QueryRejected(
                    "Unsupported SQL. Use SELECT, joins, non-recursive CTEs, filters and aggregates only."
                )
            if isinstance(node, exp.With) and node.args.get("recursive"):
                raise QueryRejected("Recursive queries are not allowed.")
            if isinstance(node, exp.Anonymous) and node.name.lower() not in FUNCTIONS:
                raise QueryRejected(
                    "This function is not in the read-only function allowlist."
                )
            if isinstance(node, exp.DataType) and str(node.this.value) not in TYPES:
                raise QueryRejected(
                    "Only built-in scalar and JSON casts are supported."
                )
        for scope in traverse_scope(tree):
            if not isinstance(scope.expression, (exp.Select, exp.SetOperation)):
                raise QueryRejected(
                    "Unsupported table grouping. Use explicit FROM and JOIN clauses."
                )
            for alias, (reference, source) in scope.selected_sources.items():
                if isinstance(reference, exp.Table):
                    resolved_tables.add(id(reference))
                if not isinstance(source, exp.Table):
                    continue  # A validated CTE/subquery, not a physical relation.
                resolved_tables.add(id(source))
                if (
                    not isinstance(source.this, exp.Identifier)
                    or source.db
                    or source.catalog
                    or source.name not in relations
                ):
                    raise QueryRejected(
                        "Query only the unqualified library tables shown in Schema."
                    )
                projection = exp.select(
                    *(
                        exp.column(c["name"], quoted=True)
                        for c in relations[source.name]
                    )
                ).from_(
                    exp.Table(
                        this=exp.to_identifier(source.name, quoted=True),
                        db=exp.to_identifier(schema, quoted=True),
                    )
                )
                source.replace(
                    projection.subquery(alias=exp.to_identifier(alias, quoted=True))
                )
        if original_tables - resolved_tables:
            # A grouped relation such as FROM ((table)) is not always a scope
            # source in SQLGlot. Never let an unresolved table reach PostgreSQL,
            # where an unqualified name could resolve in pg_catalog.
            raise QueryRejected(
                "Unsupported table grouping. Use explicit FROM and JOIN clauses."
            )
        return tree.sql(
            dialect="postgres", comments=False, unsupported_level=ErrorLevel.RAISE
        )
    except QueryRejected:
        raise
    except (
        sqlglot.errors.SqlglotError,
        RecursionError,
        ValueError,
        TypeError,
        AttributeError,
    ):
        raise QueryRejected(
            "SQL could not be parsed safely. Check its syntax or simplify it."
        ) from None


class DatabaseExplorer:
    """One read-only query at a time per Core process; no persistence of queries."""

    def __init__(self, engine: Engine):
        if engine.dialect.name != "postgresql":
            raise ValueError("Database inspection requires PostgreSQL")
        self.engine = engine
        self._admission = BoundedSemaphore(1)

    @contextmanager
    def _read(self):
        from sqlalchemy import text
        from sqlalchemy.exc import SQLAlchemyError

        try:
            with (
                self.engine.connect().execution_options(
                    isolation_level="REPEATABLE READ"
                ) as conn,
                conn.begin(),
            ):
                conn.execute(
                    text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                )
                conn.execute(text(f"SET LOCAL statement_timeout = '{TIMEOUT_MS}ms'"))
                conn.execute(text("SET LOCAL lock_timeout = '250ms'"))
                conn.execute(text("SET LOCAL work_mem = '4MB'"))
                schema = conn.execute(text("SELECT current_schema()")).scalar_one()
                # Resolve allowed functions/operators in pg_catalog only. Tables
                # are fully qualified by compile_query, never search_path.
                conn.execute(text("SET LOCAL search_path = pg_catalog"))
                try:
                    yield conn, schema
                finally:
                    conn.rollback()  # Never commit; also removes SET LOCAL.
        except SQLAlchemyError as exc:
            state = getattr(getattr(exc, "orig", None), "sqlstate", "")
            messages = {
                "57014": "Query timed out. Narrow its scope or simplify its joins.",
                "55P03": "The library is busy. Retry after processing finishes.",
                "42703": "Unknown column. Check Schema for available columns.",
                "42601": "PostgreSQL rejected the generated query syntax.",
                "42883": "That operation is not supported for these column types.",
                "22012": "Division by zero. Adjust the query expression.",
                "25006": "The database rejected a write attempt; nothing was changed.",
            }
            raise QueryUnavailable(
                messages.get(
                    state,
                    "The read-only query could not run. Check the database connection and query types.",
                )
            ) from None

    @staticmethod
    def _relations(conn: Connection, schema: str) -> dict[str, list[dict[str, str]]]:
        from sqlalchemy import text

        rows = conn.execute(
            text("""SELECT c.relname AS table_name,a.attname AS name,
            pg_catalog.format_type(a.atttypid,a.atttypmod) AS type
            FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid
            JOIN pg_catalog.pg_type t ON t.oid=a.atttypid
            JOIN pg_catalog.pg_namespace tn ON tn.oid=t.typnamespace
            WHERE n.nspname=:schema AND c.relkind IN ('r','p') AND a.attnum>0 AND NOT a.attisdropped
            AND tn.nspname='pg_catalog' ORDER BY c.relname,a.attnum"""),
            {"schema": schema},
        ).mappings()
        result = {}
        for row in rows:
            if (
                row["table_name"] in RELATIONS
                and row["name"] in RELATIONS[row["table_name"]].split()
            ):
                result.setdefault(row["table_name"], []).append(
                    {"name": row["name"], "type": row["type"]}
                )
        return result

    def schema(self) -> dict:
        with self._read() as (conn, schema):
            tables = self._relations(conn, schema)
        return {
            "available": True,
            "backend": "postgres",
            "tables": [
                {"name": name, "columns": columns} for name, columns in tables.items()
            ],
            "limits": {
                "rows": ROW_LIMIT,
                "columns": COLUMN_LIMIT,
                "cell_characters": CELL_LIMIT,
                "bytes": BYTE_LIMIT,
                "statement_timeout_ms": TIMEOUT_MS,
            },
        }

    def query(self, sql: str, *, limit: int = 100) -> dict:
        if type(limit) is not int or not 1 <= limit <= ROW_LIMIT:
            raise QueryRejected("Choose a row limit between 1 and 200.")
        if not self._admission.acquire(blocking=False):
            raise QueryBusy(
                "A database query is already running. Retry when it finishes."
            )
        started = time.monotonic()
        try:
            with self._read() as (conn, schema):
                statement = compile_query(sql, schema, self._relations(conn, schema))
                # LIMIT 0 discovers labels without transferring any data. Assign
                # ordinal aliases so duplicate result labels remain unambiguous.
                description = conn.exec_driver_sql(
                    f'SELECT * FROM ({statement}) AS "__osii_description" LIMIT 0',
                    execution_options={"no_parameters": True},
                )
                names = list(description.keys())
                description.close()
                if not 1 <= len(names) <= COLUMN_LIMIT:
                    raise QueryRejected("Select between 1 and 32 result columns.")
                aliases = ",".join(f'"c{i}"' for i in range(len(names)))
                cells = ",".join(
                    f'pg_catalog.left(pg_catalog.to_jsonb(q."c{i}")::text,{CELL_LIMIT + 1})'
                    for i in range(len(names))
                )
                result = conn.exec_driver_sql(
                    f"SELECT {cells} FROM ({statement}) AS q({aliases}) LIMIT {limit + 1}",
                    execution_options={"no_parameters": True},
                )
                rows, used, truncated_cells, limited = [], 0, 0, False
                try:
                    for raw in result:
                        if len(rows) == limit:
                            limited = True
                            break
                        row = {}
                        for i, value in enumerate(raw):
                            if value is None:
                                cell = None
                            elif len(value) > CELL_LIMIT:
                                cell = value[:CELL_LIMIT] + "… [cell truncated]"
                                truncated_cells += 1
                            else:
                                try:
                                    cell = json.loads(
                                        value, parse_float=str, parse_int=_safe_integer
                                    )
                                except (ValueError, RecursionError):
                                    cell = value
                            row[f"c{i}"] = cell
                        size = len(
                            json.dumps(
                                row, ensure_ascii=False, allow_nan=False
                            ).encode()
                        )
                        if used + size > BYTE_LIMIT:
                            limited = True
                            break
                        rows.append(row)
                        used += size
                finally:
                    result.close()
            return {
                "columns": [
                    {"key": f"c{i}", "label": str(name)[:200], "data_type": "json"}
                    for i, name in enumerate(names)
                ],
                "rows": rows,
                "row_count": len(rows),
                "limited": limited,
                "truncated_cells": truncated_cells,
                "elapsed_ms": round((time.monotonic() - started) * 1000),
                "read_only": True,
            }
        finally:
            self._admission.release()
