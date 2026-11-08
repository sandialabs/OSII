# File inventory and progressive processing

File inventory is included in normal OSII-local on one workstation or SSH-accessible
node, using a
canonical SQLite database on that machine's **local disk**. Originals stay in
read-only mounted source directories. No PostgreSQL or corporate hosted service
is required. OSII-local has no user accounts, roles, or login. Anyone using it
must be entitled to see the entire inventory
and its extracted content; this workflow does not mirror individual share ACLs.

## Start the dashboard

Set these values in `.env`, using an existing source and a local runtime path:

```dotenv
OSII_SOURCE_DIR=/mnt/team-documents
OSII_RUNTIME_DIR=/local-disk/osii-runtime
OSII_INVENTORY_DB=/local-disk/osii-runtime/inventory.sqlite3
OSII_START_TOOLBOX=false
```

Run `make dev`, or `.\scripts\osii.ps1 dev` on Windows, and open **File inventory**
in the normal dashboard. The regular API, sidecar intake worker, metadata inventory
worker, MCP, and other tools run together. No branch or storage-mode switch is
needed. `OSII_START_TOOLBOX=false` is an optional startup setting, not an
inventory requirement.

The inventory database defaults to `OSII_ROOT/state/inventory.sqlite3`; the
optional `OSII_INVENTORY_DB` overrides it. An explicit legacy `OSII_VOLUME_DB`
still opens the earlier pilot database without migrating or deleting it. Both
API and worker must use the same path. The database remains separate from the
rebuildable sidecar catalog. Sidecar Files, Search, Chat, Topics, and Intake keep
using the existing `.osii` library. Bounded processing initiated inside File
inventory stores its results in the inventory database; it does not implicitly
import them into sidecar search or duplicate existing libraries. Metadata scans
alone read directory entries and stat metadata, never file contents, content
hashes, OCR, or model endpoints.

The dashboard registers the configured source when it is available. Register
additional, non-overlapping source roots in **Sources and discovery**. Once a
source is registered, its catalog remains available when the share disconnects.
If a root's filesystem identity changes, scanning fails conservatively; reconnect
the original root. There is no automatic rebinding to a different dataset.

1. Start a metadata scan. Browse partial results while it proceeds, then refresh
   the inventory totals. Scan progress counts completed directories.
2. Apply filters for source, folder, filename, extension, dates, size, and text
   state. Totals are observed file counts and logical bytes, including duplicates;
   they do not estimate physical allocation or prove complete coverage.
3. Preview a bounded selection or reproducible sample. Sampling interleaves
   folder, extension, size band, and modification-year band, with up to two
   entries per group by default. Both the file and byte budgets apply. A selection
   freezes membership and inventory revisions in the database.
4. Explicitly process that selection. Baseline endpoints are extraction `8092`,
   OCR `8080`, synthesis `8093`, and enrichment `8094`, all on `127.0.0.1`.
   These are Processor API v1 services. Only explicit processing reads content
   and contacts a processor. The baseline synthesis produces cited excerpts,
   not an AI-written collection summary.
5. Inspect text, provenance, verified originals, products, diagnostics, and sample
   reports. OCR and downstream stages are independent operations. Successful
   extraction survives their failure. Search covers current extracted text only.

Large directories use bounded enumeration batches and persistent work queues.
After interruption, an unfinished directory is enumerated again. Completed
directories need not be repeated. Replay uses a new observation token, so files
that disappeared between attempts are handled correctly. Failed or partial
directory enumeration never establishes that unseen files were deleted.

## Headless operation and SSH

The CLI uses the same Core operations as the dashboard. Run these from the
repository root; use the same `--db` path for every command:

```bash
uv run --frozen --package osii python -m osii.volume --db /local-disk/osii/volume.sqlite3 register /mnt/team-documents
uv run --frozen --package osii python -m osii.volume --db /local-disk/osii/volume.sqlite3 scan 1
```

`scan` queues work; it does not run the worker. In a persistent terminal session
such as `tmux`, run:

```bash
uv run --frozen --package osii python -m osii.volume --db /local-disk/osii/volume.sqlite3 work
```

On a Windows workstation, run the same `uv` commands in PowerShell. On an SSH
node, keep `make dev` or the worker in a persistent session so closing SSH does
not terminate it. A browser is never needed to keep work running. Forward the
dashboard port to your workstation with `ssh -L 5173:127.0.0.1:5173 user@node`,
then open `http://127.0.0.1:5173`. Keep the API and dashboard bound to loopback;
this single-operator pilot is not an authenticated multi-user hosted service.

Further commands, with the database option abbreviated here:

```bash
python -m osii.volume --db /local-disk/osii/volume.sqlite3 summary --suffix pdf
python -m osii.volume --db /local-disk/osii/volume.sqlite3 select --suffix pdf --sample --seed pilot --max-files 100 --byte-budget 1073741824
python -m osii.volume --db /local-disk/osii/volume.sqlite3 process 1 --endpoint http://127.0.0.1:8092 --max-seconds 3600
python -m osii.volume --db /local-disk/osii/volume.sqlite3 status 2
python -m osii.volume --db /local-disk/osii/volume.sqlite3 report 2
python -m osii.volume --db /local-disk/osii/volume.sqlite3 control 2 pause
python -m osii.volume --db /local-disk/osii/volume.sqlite3 control 2 resume
python -m osii.volume --db /local-disk/osii/volume.sqlite3 search '"public records"'
python -m osii.volume --db /local-disk/osii/volume.sqlite3 document 1
python -m osii.volume --db /local-disk/osii/volume.sqlite3 export /local-disk/osii/inventory.jsonl
```

Use the environment's Python, or prefix the examples with
`uv run --frozen --package osii`. List/search/history commands return bounded
pages; `list`, `search`, and `events` accept `--cursor`. JSONL export streams all
matching entries and refuses to overwrite a destination or write into a source.
An export made while scanning is live is not a consistent snapshot.

## Evidence and recovery

An inventory entry identifies a source location without requiring a content hash.
Only selected processing reads and hashes bytes. The known native parser may
reuse results for identical content and format; arbitrary processors also key
results by their request metadata. Every location and revision retains
its own provenance link. Extraction response, text, hash, and processor identity
are canonical database records; the FTS5 index is derived.

Changes to size, times, entry type, or availability invalidate the current
extraction link. Metadata is a freshness hint, not proof of identical content;
rescanning alone cannot detect every same-metadata content change. Selected
processing and original downloads hash the content. Historical extractions and
products remain inspectable; products tied to a different current extraction
are marked stale. Symbolic links are inventoried but never traversed, and
archives are not expanded.

Jobs have coordinator leases, heartbeats, and transactional commits. Only one
coordinator processes work at a time, even if another worker is started.
Termination or lease expiry requeues unfinished work. Automatic recovery stops
a file after three interrupted attempts; explicit resume authorizes a fresh set
of attempts. A lost processor response can still mean the processor performed
work. This is not exactly-once execution or a monetary spending guarantee.

File and byte selection budgets are hard membership limits. Processing accepts
up to 50 MiB per source and bounded responses/text scopes; larger sources remain
inventoried. Time budgets are checked between files and bound individual HTTP
timeouts; native filesystem calls may block longer on a failed share. Pausing
or cancelling takes effect at the next safe boundary and retains committed work.
After a time budget is exhausted, create a new bounded run; use the metadata-only
filter to select files without a current extraction.

Reports show usable text yield, empty/OCR candidates, failures, reused results,
elapsed processing time, and format/size groups. Estimated time for matching
inventory is a labeled heuristic, not a statistical confidence interval. Scanned
PDFs and genuinely empty documents both appear as empty/OCR candidates. Measure
actual sample behavior before increasing budgets. Automatic volume-wide model
processing, semantic indexing, cross-document research, and distributed workers
are deferred.

## Backups, schema changes, and scale checks

Never place the live database on SMB/NFS or share it between hosts. SQLite WAL
requires same-host access; use the API or CLI on the owning host. Keep backups
on suitable separate storage. This requirement also applies to SSH nodes with
network-mounted home directories: choose genuinely local scratch/persistent disk.
OSII cannot reliably establish every filesystem's remote/local characteristics.

```bash
python -m osii.volume --db /local-disk/osii/volume.sqlite3 backup /backup/osii-volume.sqlite3
python -m osii.volume --db /local-disk/osii/restored.sqlite3 rebuild-search
```

`backup` uses SQLite's online backup operation and refuses an existing destination
or a source-root destination. Do not copy just a live database file while its WAL
is active. Restore the backup to local disk, point `OSII_INVENTORY_DB` at it, and
verify source roots, text, provenance, and search. Retain matching originals
separately. Unsupported schemas and database failures stop operations; they
never trigger an empty-store fallback or rebuild of canonical evidence.

Run `pytest osii-core/tests/test_volume.py` for recovery and provenance checks.
The manual benchmark measures one and five million synthetic inventory rows,
plus optional real filesystem traversal, in isolated processes:

```bash
PYTHONPATH=osii-core osii-env/bin/python osii-core/tests/benchmark_volume.py --counts 1000000 5000000 --filesystem-files 100000
```

It reports enumeration/load time, page and aggregate query time, sampling time,
database size, and peak resident memory. Synthetic rows validate database scale,
not SMB throughput. Repeat discovery on representative shared storage before
claiming production capacity. The benchmark's memory measurement uses POSIX
`resource`; the application and automated tests support Windows independently.

Initial macOS development measurements on 5 November 2026, with temporary local
storage, are a baseline rather than a corporate-drive capacity claim:

| Inventory | Peak RSS | Filtered 100-row page | Full totals | Stratified selection |
| --- | ---: | ---: | ---: | ---: |
| 1 million synthetic entries | 56.1 MiB | 0.7 ms | 0.2 s | 1.4 s |
| 5 million synthetic entries | 58.6 MiB | 1.0 ms | 11.2 s | 12.7 s |

The five-million-entry database occupied about 1.46 GiB. Real traversal of
100,000 empty local files took 1.8 seconds with 56.5 MiB peak RSS, excluding
fixture creation. These checks do not measure extraction or network storage.
