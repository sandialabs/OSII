# Read-only database explorer

Use **Toolbox → Database explorer — read-only** to inspect the PostgreSQL
library with SQL. Select a table to see its available columns, choose **Use
table query** to prepare a query, then press **Run SELECT**. Preparing a query
does not execute it. Results use the existing scrollable, sortable table viewer;
**Clear** removes the editor text and displayed results.

This is a diagnostic for people who know SQL, not an automatic model/agent tool
or a general database administration console. It needs no extra service.

## Availability and permissions

- **OSII-local:** available only with the explicitly selected
  PostgreSQL backend. Local remains login-free and loopback
  only. Normal sidecar installations are unchanged: this tool does not query
  either the derived sidecar catalog or the separate file-inventory SQLite.
- **OSII-server:** administrators only, including schema discovery and direct
  API calls. Readers and curators cannot use the route or its API. Existing
  session, temporary-password, origin and CSRF checks apply. Administrators also
  have a **Database explorer** navigation item.

No schema migration or data import is required. Restart Core after updating
dependencies (`osii[postgres]` locally or `osii[server]` on the server).

## What can I query?

The **Schema** panel is the authoritative list for the running library. Only
existing, explicitly approved columns from these library tables are exposed:

| Tables | Information |
| --- | --- |
| `documents`, `extractions`, `chunks` | Source identity, text, metadata, extraction responses, chunks and vectors |
| `artifacts`, `scope_products`, `scope_revisions` | Saved products, scopes, revisions and provenance |
| `collections`, `datasets` | Collection membership, ownership/visibility and dataset revision |
| `jobs` | IDs, kind, status, attempts, worker, lease and creation time; **not payloads or logs** |
| `import_files` | Import IDs, relative paths and hashes; **not binary source content** |

Account/password tables, sessions, provider configuration, credentials, audit
records, system catalogs and unrelated tables are not available. New columns
are not automatically exposed. Views, foreign tables and custom column types
are excluded. Saved library text/products can themselves contain sensitive
source information; administrative access is not a redaction mechanism.

Start small:

```sql
SELECT filename, source_relpath
FROM documents
ORDER BY source_relpath
LIMIT 25
```

Supported SQL includes a single `SELECT`, joins, filters, non-recursive `WITH`,
`UNION`/`INTERSECT`/`EXCEPT`, grouping, common aggregates (`COUNT`, `SUM`, `AVG`,
`MIN`, `MAX`), basic arithmetic/text operations and JSON field access (`->`,
`->>`). Use **unqualified** table names shown in Schema. Some otherwise valid
PostgreSQL expressions are intentionally unsupported; the UI reports this
without echoing the SQL or database connection details.

Writes, DDL, `COPY`, `EXPLAIN`, transaction/session commands, recursive queries,
locking clauses, arbitrary functions and system relations are rejected. This
is deliberately narrower than full PostgreSQL SQL.

## Read-only safeguards and limits

Core parses SQL with the pinned optional PostgreSQL dependency SQLGlot. It
validates an allowlisted syntax tree, rewrites every base relation to an explicit
column projection in the active library schema, and executes **generated SQL**,
not the submitted text. Identifier casing follows PostgreSQL; unresolved
relations and parenthesized table-grouping forms are rejected (use explicit
`FROM`/`JOIN` clauses). Only `pg_catalog` is on the query search path, so a
similarly named function in the library schema cannot intercept built-in calls.

Every query transaction is PostgreSQL **READ ONLY** and always rolled back,
including after errors. Pool connections do not retain query-specific settings.
Bounds are:

- One admitted query per Core process; a concurrent request receives HTTP 429.
- 16,000 input characters and 1,000 parsed syntax nodes.
- Two seconds per database statement, 250 ms lock timeout and 4 MB `work_mem`.
- At most 200 returned rows, 32 columns and approximately 1 MB of row data.
- Each cell capped to 2,048 JSON-text characters **inside PostgreSQL before
  transfer**. Shortened cells are visibly marked; row/byte limits are reported.

These are preview limits, not pagination or a bulk export. Decimal values and
integers beyond JavaScript's safe integer range are displayed as strings to
avoid silently losing precision. Duplicate column labels have separate keys.

Timeouts and `work_mem` reduce accidental load; they are not an absolute CPU,
memory or availability sandbox. Use trusted administrators, normal PostgreSQL
role restrictions and deployment resource limits. The tool does not defend
against a malicious database owner changing built-ins or relation definitions.

SQL and results are not written to browser storage, canonical library products,
or OSII query history. Leaving the page discards its in-memory results. Server
audit records contain the administrator ID, outcome and SHA-256 query
fingerprint, **not SQL or results**; a failed audit prevents a successful
response. Session/audit bookkeeping is separate from the read-only query
transaction. PostgreSQL or infrastructure statement logging can still retain
SQL: operators must configure that logging to their information-handling policy.

## Reusable Core interface and HTTP boundary

`osii.domain.storage.database_query.DatabaseExplorer(engine)` accepts an
existing SQLAlchemy PostgreSQL engine. `schema()` discovers the approved
projection; `query(sql, limit=100)` returns columns, ordinal-keyed rows, elapsed
time and preview-limit flags. It neither creates schemas nor knows about users,
launchers, processors or HTTP. Optional PostgreSQL dependencies are not installed
by the ordinary sidecar workflow.

`osii.api.database_routes.create_database_router` requires an explicit
authorization dependency from the composing application. Server supplies its
existing administrator dependency and audit callback; local supplies its
login-free operator boundary. The shared dashboard is only an API client.

| Operation | Request |
| --- | --- |
| Discover schema and limits | `GET /api/admin/database/schema` |
| Run an explicit read-only query | `POST /api/admin/database/query` with `{"sql":"SELECT count(*) FROM documents","limit":100}` |

Server POST requests require the logged-in session cookie and `X-CSRF-Token`.
Unavailable sidecar mode returns `available=false` on schema discovery and HTTP
409 on execution. Rejected SQL returns 422, concurrent queries 429, and database
errors/timeouts or audit failure 503 with sanitized messages. Raw database errors
are not returned. There is no query registration as a Processor API capability,
no direct database access for processor module containers, and no model-driven execution.

See PostgreSQL's [read-only transaction and timeout settings](https://www.postgresql.org/docs/18/runtime-config-client.html)
and the [SQLGlot AST documentation](https://sqlglot.com/sqlglot.html).
