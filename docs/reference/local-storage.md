# Local storage: sidecars or PostgreSQL

**Nothing changes for the normal installation:** `make dev` (Windows:
`.\scripts\osii.ps1 dev`) saves library data in portable `.osii` sidecars.
An ambient `DATABASE_URL` does not change that choice.

You can explicitly select PostgreSQL for the **whole local Workbench**, not
just Python reads: Intake, incremental browsing, source/PDF viewing, extraction
variants, synthesis, standard enrichment products, edits and histories,
collections, search, chat, research, Activity and pause/cancel/retry controls.
The API and worker use the same backend; the dashboard and MCP remain API clients.
This does **not** turn local OSII into the hosted server or add users or login.

## What lives where?

| Data | Sidecar default | Optional PostgreSQL |
| --- | --- | --- |
| Original documents | Your existing folder or mounted share | Same; never copied into PostgreSQL |
| Text, locations, provenance, products, edits and collections | Canonical `.osii` files | PostgreSQL records and revision history |
| Processing jobs and checkpoints | Operational `state/jobs.sqlite3` | PostgreSQL `jobs` table |
| Retrieval | Rebuildable BM25/FAISS files | Saved chunks/vectors; in-process BM25/cosine ranking |
| File metadata inventory | Separate canonical local SQLite | **The same independent SQLite**, never reset or migrated |
| Models, tool settings and credentials | Active configuration directory | Same; not stored in the library database |

`DATABASE_URL` selects the PostgreSQL library; changing `OSII_RUNTIME_DIR` alone
does not select a different database. `OSII_ROOT` is still needed for local
inventory/runtime state. In PostgreSQL mode
Core does not mirror new products into sidecar files or silently read an old
sidecar library. Selecting sidecars again reopens that old library; it does not
copy newer PostgreSQL changes back. Portable collection ZIP export/import is
available explicitly from Collections, including revisions and sensitivity labels,
without original files or credentials.

## Start a new PostgreSQL library

Stop OSII first. Provision PostgreSQL separately, with a dedicated **empty**
database/schema and a role allowed to create tables. Do not use an OSII-server
database, or a database containing unrelated application tables. No database
service, accounts, schema initialization or data migration is started by `dev`.

In your ignored repository `.env`, keep the source, runtime and configuration
paths you already use; change/add only:

```dotenv
OSII_STORAGE_BACKEND=postgres
DATABASE_URL=postgresql://osii_user:replace-me@127.0.0.1:5432/osii_local
```

Replace the connection details. Percent-encode special characters in the password.
Process environment variables override `.env`; remove stale overrides if needed.
Never commit the URL or paste it into a diagnostic log.

Run from the repository root on **macOS/Linux or Windows PowerShell**:

```text
uv run --env-file .env --python 3.12 --package osii --extra postgres python -m osii.storage_cli init
uv run --env-file .env --python 3.12 --package osii --extra postgres python -m osii.storage_cli status
```

Initialization creates only the account-free local schema, in one transaction.
It refuses an occupied schema. Startup checks the explicit local schema marker
and version; a missing/unavailable/incompatible database fails closed, without
creating tables, importing data or switching to sidecars.

For an empty library, start normally:

```bash
make dev
```

Windows:

```powershell
.\scripts\osii.ps1 dev
```

Both launchers install the optional PostgreSQL dependencies only when selected.
Core, worker, baseline processors and Toolbox keep the normal host workflow.
No separate image build, launcher menu or authentication setup is necessary.

## Explicit one-way import of an existing sidecar library

Keep OSII and all other writers stopped throughout import. Back up the sidecar
directory first. Use the `.osii` directory itself, **not** the originals folder.
The destination must be initialized and empty; import before starting Workbench.

Preview (read-only, no database connection required):

```text
uv run --env-file .env --python 3.12 --package osii --extra postgres python -m osii.storage_cli import-sidecars "./osii-data/.osii"
```

Apply only after checking the source path and preview:

```text
uv run --env-file .env --python 3.12 --package osii --extra postgres python -m osii.storage_cli import-sidecars "./osii-data/.osii" --apply
```

These commands also work in PowerShell; Windows paths such as
`"C:\OSII\library\.osii"` are accepted. Import preserves document IDs, source
paths, exact canonical/preferred text, saved extraction variants, grounding,
products, collection membership, edits and revision histories. Internal revision
IDs are namespaced where required; their original IDs remain in provenance.
Legacy canonical attachments are retained in an import archive inside PostgreSQL
so normalization does not discard unrecognized file-based content.

The importer uses an explicit allowlist. It excludes source files, credentials,
configuration, catalogs, caches, queues and search indexes. Symlinks and legacy
`.collections/collections.sqlite` membership are rejected rather than silently
omitted; export legacy collections to the portable collection format first.
Source changes during import or invalid/conflicting data roll back the entire
destination transaction. The source directory is never written, moved or deleted.
Import is not an automatic synchronization or a destructive migration.

Lexical chunks are rebuilt from saved preferred text during import, without
reading originals or contacting a model. After import, start `dev` and explicitly
rebuild embeddings in Intake. Old jobs
are not resumed. Retain the original sidecars as a backup; later PostgreSQL edits
will not be present there unless explicitly exported.

## Processing, recovery and limits

- Each extracted document is committed with its job checkpoint and becomes
  browsable before later files finish. Optional synthesis/enrichment and embedding
  backfill remain under the same Intake run's cooperative pause/cancel control.
- Model calls are bounded batches. Completed embedding batches are checkpointed
  for retry; public Activity responses do not expose their vectors. Edits refresh
  lexical chunks and invalidate embeddings without rewriting extraction evidence.
  Promoting a different extraction in PostgreSQL retires the old preferred-text
  override into history rather than applying its segment edits to new evidence.
  The default sidecar workflow's existing preference policy is unchanged.
  Graceful shutdown releases an owned claim; after a force-stop, a local claim
  expires within 15 seconds and can be recovered without stealing a live worker's job.
- Provider, endpoint/model binding, dimensions, normalization and chunking identify
  a vector space. Incompatible changes require an **explicit index rebuild**.
  Hybrid search falls back to BM25 if the matching embedder is unavailable;
  semantic-only search fails clearly. Hashing is lexical, never labeled semantic.
- This composition has one active vector space, using the shared PostgreSQL chunk
  contract. Rebuild replaces derived vectors; it does not delete document products.
  Ranking still loads the selected scope into memory. PostgreSQL selection alone
  is not a claim of hundred-thousand-document retrieval scalability or a new
  database-native vector-search implementation.
- File deletion previews the affected records and blocks active referencing runs.
  The default keeps originals. Deletion affects this library only, including its
  affected raw import archives; old sidecar copies, other libraries, backups and PostgreSQL
  WAL are **not** securely erased. Review sensitivity handling separately.

To return to sidecars, stop OSII, set `OSII_STORAGE_BACKEND=sidecar`, and restart.
Neither store is converted, erased, or kept in sync. A database failure never
triggers this switch automatically. Use `storage_cli status` to check the selected
schema; database credentials and SQL parameter values are omitted from errors.

## Verify without real documents or models

Set `OSII_READ_TEST_DATABASE_URL` to a **disposable test database** whose role can
create schemas. Tests create/drop unique schemas, not a user's library. Run:

```text
uv run --python 3.12 --package osii --extra postgres --extra dev python -m pytest osii-core/tests/test_local_postgres.py osii-core/tests/test_library_reads.py osii-core/tests/test_processing_commits.py osii-core/tests/test_library_authoring.py osii-core/tests/test_retrieval_jobs.py -q
```

The local integration tests use real PostgreSQL, real baseline Processor API HTTP
services and controlled fake model responses. No model downloads or container
runtime are required. Shared port tests run against sidecars and PostgreSQL.
