# Shared document and artifact reads

Core has a read-only `LibraryReader` contract under `osii.domain.read.contracts`.
The same contract and tests are used by local sidecars and the PostgreSQL hosted
composition. This is the first persistence boundary, not a completed backend
switch: local startup still uses sidecars, and hosted startup still requires
PostgreSQL. No `.env` storage selector or automatic migration is available.

## What the interface returns

| Operation | Result |
| --- | --- |
| `list_documents(scope, limit=100, cursor=None)` | A `Page[DocumentRecord]` with summaries, full-scope total, and next cursor |
| `get_document(file_id)` | Metadata for one document, or `None` |
| `get_representation(file_id, representation_id="preferred")` | Exact text, representation ID, typed segments with offsets/geometry, and provenance, or `None` |
| `list_artifacts(file_id, limit=100, cursor=None)` | A `Page[ArtifactRecord]` of document artifact descriptors |
| `get_artifact(file_id, artifact_id, max_bytes=...)` | An `ArtifactContent` with descriptor and bytes, or `None` |

Records are dataclasses, with no filesystem `Path`, SQLAlchemy row, or transport
response dependency. Document metadata and provenance retain their native
source-specific fields; callers should use the common named fields for portable
logic. SDK artifact wrappers are decoded to their JSON data or binary content,
so the standard table, graph, entity, and wiki formats remain usable across
stores. Complete processing responses remain SDK response envelopes when saved
as one product. Compatibility HTTP responses retain their original envelopes;
the reader does not rewrite a saved result.

`ReadScope()` means the whole library. `ReadScope("object", file_id)` selects a
document; `ReadScope("collection", collection_id)` selects members. A folder
identifier is a **source-relative directory path**, not a host path or local
folder-manifest ID. Folder membership includes descendants, with an exact
directory boundary. Product adapters resolve their existing folder IDs before
calling this contract. Object artifact reads are supported in this first slice;
aggregate artifact routing remains in existing workflows.

Pages allow 1–500 records. Documents sort by source path and file ID using binary
ordering; artifacts sort by artifact ID. Cursors are opaque and bound to the
operation/scope. Invalid or cross-scope cursors raise `ValueError`. Totals count
the entire current scope, not only records after a cursor. Concurrent changes
can affect later pages; this interface does not promise a long-lived snapshot.

Artifact reads default to a 5 MiB output limit and raise `ValueError` when it is
exceeded. Legacy full-payload HTTP adapters explicitly use `max_bytes=None` to
preserve existing behavior. This is an output guard, not a guarantee that parsing
existing product histories or PostgreSQL JSONB uses at most that much memory.

## Select an implementation explicitly

For a portable sidecar library:

```python
from pathlib import Path
from osii.domain.read.sidecar import SidecarLibraryReader

reader = SidecarLibraryReader(Path("/path/to/.osii"))
page = reader.list_documents(limit=20)
if page.items:
    representation = reader.get_representation(page.items[0].file_id)
```

Local compositions with versioned human-edited products pass the existing
`products.read_product` function as `product_reader`. This honors the committed
product manifest even if a compatibility JSON file is missing after interruption.
Viewing preferred text does not archive or register a legacy extraction. Legacy
edited segments still take precedence; their old source geometry is not assigned
to newly written text. This change does not implement a new editing/activation
workflow or alter existing write policies.

`SidecarLibraryReader` opens an existing catalog read-only and closes connections
after each operation. Without a catalog it scans object metadata, retaining only
one result page in memory; that fallback still takes a full metadata scan.
Queries do not initialize a store, rebuild/quarantine a catalog, or write to
inventory SQLite. Existing startup/maintenance owns catalog recovery.

`PostgresLibraryReader(engine, actor_id=...)` accepts the composition's SQLAlchemy
PostgreSQL engine over the existing hosted schema. Transactions are read-only;
the adapter neither creates tables nor imports server accounts or startup into
local. Install the optional `osii[postgres]` extra for direct local Python use;
the hosted `server` extra already supplies these dependencies.

Authentication remains at the hosted API boundary. All users currently share
the hosted document corpus; private collection membership additionally requires
the owner supplied to the reader. Omitting `actor_id` exposes shared collections
only. A missing connection or incompatible schema fails rather than opening a
sidecar fallback. PostgreSQL failure is not a reason to mutate local files.

## Verify parity

Use an isolated PostgreSQL database for this test. The test owns a uniquely named
schema and removes only that schema; it does not replace `public` or migrate a
library. From the repository root on macOS/Linux:

```bash
OSII_READ_TEST_DATABASE_URL=postgresql://localhost/osii_reads_test \
  uv run --frozen --python 3.12 --package osii --extra postgres --extra dev \
  python -m pytest --noconftest osii-core/tests/test_library_reads.py -q
```

On Windows PowerShell:

```powershell
$env:OSII_READ_TEST_DATABASE_URL = "postgresql://localhost/osii_reads_test"
uv run --frozen --python 3.12 --package osii --extra postgres --extra dev python -m pytest --noconftest osii-core/tests/test_library_reads.py -q
```

Use your test role/connection details in that URL. The schema-creating test role
needs permission to create schemas. `--noconftest` keeps this standalone contract
suite independent of either application's startup. Without the variable, only
PostgreSQL cases skip. CI runs the suite with a real PostgreSQL database; hosted
API tests additionally exercise the adapter against the migrated production
schema. No models, processors, containers, or original documents are needed for
the contract itself.

The [processing commit boundary](processing-commits.md) now handles document
results and folder/collection/root synthesis and enrichment products.
The [authoring/collection interfaces](library-authoring.md) add product draft
save/activation and version-checked collection commands. Broader legacy write
adoption, durable job interfaces, document-text authoring parity, and explicit
library transfer remain later work. Replacing
whole-corpus server retrieval snapshots is also separate from these read APIs.
