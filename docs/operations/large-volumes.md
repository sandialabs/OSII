# File inventory and progressive processing

Intake includes resumable discovery and frozen staging selections. The
[shared-drive Intake plan](../planning/shared-drive-intake.md) records the
implementation scope and remaining corporate-scale validation.

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

Run `make dev`, or `.\scripts\osii.ps1 dev` on Windows, and open **Intake →
Add files → Discover a shared drive** in the normal dashboard. The regular API, sidecar intake worker, metadata inventory
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

## Discovery and staged Intake

1. Select a registered source, or register an existing share/folder path. Sources
   must not overlap. Use **Quick folder selection** for a small one-off folder;
   discovery does not run a recursive HTTP preview.
2. Set scan include/exclude patterns, hidden-path policy, maximum depth, and
   whether to cross filesystem boundaries. Depth 0 reads root entries only.
   Symlinks are never followed. Rules are saved with the scan and cannot change
   on resume. Start with the default two readers (maximum eight).
3. Start discovery. The API returns a run ID without walking the share. Progress
   shows observed entries, known logical bytes, directory tasks, current branches,
   metadata failures, and last activity. It does not estimate an unknown total.
   Results and filters query local SQL, with pages of 100 names.
4. Pause, close the browser, or restart OSII. **Resume scan / retry failures**
   continues unfinished directories after reconnecting or fixing permissions.
   A new scan supersedes older scans; obsolete scans cannot overwrite newer
   observations. Partial enumeration never establishes deletion. An unfinished
   flat directory replays from its beginning with a fresh observation token.
5. Filter by path, name, extension, date, size, metadata availability, and whether
   this inventory revision was processed through staged Intake. Older cached
   observations are labeled as such; new selections include only files observed
   in the latest scan. Content-read permission is checked later in the worker.
6. Choose file/byte budgets and optionally a reproducible stratified sample.
   **Freeze selection for Intake** saves source/path, revision, source generation,
   file identity, size/times, request rules, and discovery coverage. Incomplete
   coverage requires explicit acknowledgement. Unknown-size entries are excluded.
   Defaults are 100 files and 1 GiB; Intake accepts up to 10,000 files per batch
   and 50 MiB per file. The frozen selection never grows with later discoveries.
7. Review the frozen names and use the existing Intake preset and processing
   options below. **Start intake** enqueues the normal sidecar worker. Changed,
   missing, denied, and malformed files fail individually; healthy files continue.
   Successful documents appear in Files and can feed Search, Topics, and Chat.
   No contents are read, hashed, or sent to models during freezing or enqueueing.
8. Use **Activity** for processing pause/resume/retry and file-level errors. Restore
   a saved selection by its ID after reloading. Repeating the same selection and
   request returns its existing run, including after an interrupted handoff. Use
   Activity to retry that run, or freeze a new selection for a new batch.

Processing checks the one-hour default time budget between files, then pauses
for explicit resume; the API accepts `max_processing_seconds` from 1 to 86,400
for a staged run. A filesystem call already blocked in the OS can exceed this
budget. The optional embedding step embeds only the selected documents, reuses
completed chunk checkpoints, and preserves vectors for the rest of the library.
On an embedding failure, use **Activity → Retry embeddings** to continue without
repeating completed extraction, summaries, enrichment, or embedding requests.
Source reads, extraction, summaries, and enrichment use only the frozen members.
The [incremental embeddings decision](../concepts/adr-incremental-embeddings.md)
describes snapshot consistency, legacy indexes, and checkpoint recovery.
Staged Intake writes normal document sidecars and a metadata-only frozen manifest;
it avoids legacy whole-folder rehashing and does not claim that this batch is a
complete folder manifest. The manifest records selection metadata, while document
sidecars retain actual content hashes and provenance.

If a remount changes the registered root's identity, first verify the dataset and
cancel active scans. Under **Changed mount identity**, enter the exact registered
path, acknowledge that verification, and rebind. This increments the source
generation, invalidates previous selections, preserves historical evidence, and
requires a fresh scan. Never use rebind to silently replace a dataset.

Each metadata reader runs in a separate process with a bounded two-batch channel;
one leased coordinator writes SQLite in batches of at most 500 observations.
A reader with no progress for 30 seconds is stopped and reported. Repeated stalls
open the source circuit breaker and require explicit resume. Kernel-blocked
network calls may resist termination and require restoring the mount or OS
intervention. OSII does not change mount options. This does not isolate hard
filesystem hangs during later content processing; use small batches on unreliable
shares. No automatic continuous scanning or share ACL mirroring is provided.

## Independent inventory processing

**File inventory** remains available for metadata inspection and the original
bounded Processor API experiments. Its extraction/products live in the canonical
inventory database; these are not implicitly imported into the sidecar library.
Use the Intake handoff above when the documents should appear in Files/Search.

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
For independent inventory processing, create another bounded run after a time
budget is exhausted. Staged Intake instead pauses and resumes the same frozen
batch in Activity. Use the relevant prior-processing filter to omit successes.

Reports show usable text yield, empty/OCR candidates, failures, reused results,
elapsed processing time, and format/size groups. Estimated time for matching
inventory is a labeled heuristic, not a statistical confidence interval. Scanned
PDFs and genuinely empty documents both appear as empty/OCR candidates. Measure
actual sample behavior before increasing budgets. Automatic volume-wide processing, inventory-native semantic indexing, and
distributed workers remain outside this workflow. Normal sidecar Intake keeps
its existing optional indexing and research capabilities.

## Backups, schema changes, and scale checks

Version 2 requires an explicit migration of existing version-1 inventories. Stop
OSII with Ctrl+C and wait for the inventory worker lease to end, then run:

```bash
uv run --frozen --package osii python -m osii.volume --db /local-disk/osii/inventory.sqlite3 migrate --backup /local-disk/osii/inventory-v1-backup.sqlite3
```

Use the actual inventory path from `/api/volume/runtime`. The migration checks
for an active lease, refuses to overwrite a backup, makes a SQLite backup with
owner-only permissions, and upgrades transactionally. Startup fails clearly on
an old/unknown schema; it never replaces canonical evidence. Restart `make dev`
after migration. Keep the backup until recovery has been verified.

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

Run `pytest osii-core/tests/test_volume.py osii-core/tests/test_volume_discovery.py`
for recovery, migration, staging, and provenance checks.
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


## Verification on 9 November 2026

A scan of `/Volumes/home/hk` on the NAS at `192.168.1.150` observed 2,135 PDFs,
3,912,740,792 known logical bytes, and five directory tasks with no metadata
failures. The mounted protocol was SMB (`smbfs`), not NFS. Scan acknowledgement
was 6 ms. A second scan was paused after 507 observations, survived an inventory
worker restart, and resumed through Intake to the same complete totals. A health
request during the scan returned in about 0.6 ms. These are warm/cached single-
workstation observations, not corporate throughput guarantees.

The browser froze and restored a one-file selection and started text-only Intake.
That PDF completed into normal document sidecars and was returned by keyword
search. No summaries, embeddings, or other model calls were requested. Automated
fault tests cover denied entry metadata, incomplete coverage, a stopped reader,
checkpoint replay, stale files, malformed PDFs, lost handoff acknowledgement,
explicit rebinding, migration backup, and processing pause/resume. Real network
disconnection and a kernel-blocked NFS call were not induced on this NAS.

The updated synthetic million-row benchmark completed with a 0.9 ms late page,
0.19 s aggregate summary, 1.56 s bounded sample, and 56.6 MiB peak process RSS;
the database was about 328 MiB. This checks SQL paging/filtering/staging memory,
not mixed ACLs or filesystem traversal throughput. Validate representative NFS
branches and compare reader counts before a 35 TB rollout.
