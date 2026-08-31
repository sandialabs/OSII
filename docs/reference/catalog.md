# Rebuildable catalog

OSII's canonical record remains the portable `.osii` file tree. The normal
metadata read path is `.osii/state/catalog.sqlite3`, a derived SQLite catalog
using foreign keys, WAL mode, a busy timeout, and schema versioning.

The catalog indexes documents, paths, hashes, MIME types, processing state,
extractor identity, folders, canonical collections and membership, artifact
paths, and available semantic indexes. It never contains the only copy of user
text, provenance, a synthesis, or an enrichment.

Core writes canonical files atomically first and then reconciles the catalog.
Completed objects are upserted one at a time, so Files can show each document
during a long Intake. Startup creates a missing catalog automatically. An
integrity failure quarantines the corrupt database as
`catalog.corrupt-<timestamp>.sqlite3` and rebuilds it; filesystem reads remain
the compatibility fallback while that happens.

Legacy `.osii/.collections/collections.sqlite` data is migrated once into:

```text
.osii/collections/<collection-id>/
├── collection.toml
└── members.jsonl
```

The old database is retained for recovery but is no longer authoritative.

Commands:

```bash
make catalog-verify
make catalog-rebuild
```

PowerShell uses `.\scripts\osii.ps1 catalog-verify` and `catalog-rebuild`.

The existing `/api/osii/files` and `/api/osii/folders` endpoints remain. New
catalog endpoints add stable cursor pagination and filtering:

- `GET /api/catalog/status`
- `POST /api/catalog/rebuild`
- `GET /api/catalog/files?limit=100&cursor=...&status=done&suffix=pdf&path=reports/&text=calibration`
- `GET /api/catalog/folders`
- `GET /api/catalog/artifacts?scope_type=object&scope_id=...&kind=enrichment`

The dashboard's flat file grids provide an immediate browser-local filename,
path, and file-type filter. They can sort the returned files alphabetically,
by original modification date, or by original file size. These controls do not
alter canonical `.osii` data or require a separate search index.

Run the synthetic 1,000/10,000-document benchmark with:

```bash
uv run --package osii python ai-ready-ingest/tests/benchmark_catalog.py
```
