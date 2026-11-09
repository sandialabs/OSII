# Resumable shared-drive discovery and Intake staging

Status: proposed implementation plan. The immediate preview fix below is
implemented; the large-volume integration and concurrency work are planned.

## Goal and current findings

A user should be able to discover a shared drive incrementally, filter what is
visible, freeze a bounded intake selection, and resume discovery or processing
after closing the browser, restarting OSII, or losing the share. OSII-local
remains a single-operator application without user accounts. The operating
system's mounted-share credentials determine source access.

Capacity planning depends on entry count, directory shape, metadata latency,
and permission boundaries, not just the drive's total bytes. A 35 TB volume
might contain thousands of large files or tens of millions of small files.
Start by measuring representative branches before scheduling the entire drive.

The quick Intake preview previously hashed every selected source, read the
embedding mapping wholesale, and performed blocking I/O inside async request
handlers. It now uses recorded catalog identities and filesystem metadata,
streams index membership only when useful, and runs blocking handlers in the
API's thread pool. Source hashes and final deduplication remain processing work.
The UI marks the plan as an estimate, cancels obsolete browser requests, and
shows an actionable error after 30 seconds rather than an indefinite spinner.
A browser timeout does not cancel a filesystem call already running in Core.

On 8 November 2026, `/Volumes/home/hk` contained 2,135 matching PDFs when recursive
selection was enabled. The active mount reported SMB (`smbfs`), not NFS.
After the first fix, preview took about 21 seconds while health checks stayed
below 12 ms. Reusing directory-entry metadata reduced a subsequent preview to
about 12.6 seconds. Cache state affects those measurements; these are not NFS
or corporate-capacity benchmarks. No extraction or model processing was started.

## Reuse the existing scanner

`osii.volume` already provides a useful foundation:

- A canonical inventory database on local disk, independent of the rebuildable
  sidecar catalog. Do not put either live SQLite database on SMB/NFS.
- Persistent source roots, scan runs, pending directories, observations,
  selections, run controls, coordinator leases, and heartbeat recovery.
- Metadata writes in batches of 500, paged queries, and file/byte-limited samples.
- Re-enumeration of an interrupted directory with a fresh observation token.
  Completed directories survive restart. Partial or failed enumeration cannot
  establish that unseen files were deleted.
- Separate metadata discovery and explicit content extraction. Discovery never
  opens documents, hashes content, invokes OCR/models, or expands archives.

The gaps are important: discovery currently has one coordinator, a failed child
stat can fail its whole directory, long directories are replayed rather than
resumed at a portable iterator offset, and File inventory processing is separate
from normal sidecar Intake. Reuse and improve this code rather than add another
scanner, storage mode, branch, or hosted service.

## 1. Give Intake two explicit source-selection paths

Keep quick folder selection for modest sources. Add **Discover a shared drive**
as a first-class Intake step that opens or resumes the existing inventory scan.
Users can enter a root, choose include/exclude rules and traversal boundaries,
and start discovery without choosing an AI model or waiting for full coverage.
Suggest this route after a slow quick selection or when a source already has a
large inventory. Do not attempt a full recursive HTTP preview before suggesting it.

Return a scan ID immediately. Show observed files, directories completed/pending,
known logical bytes, denied/unavailable paths, elapsed time, last activity, and
current branches. Results are usable while scanning. Display partial coverage,
unknown sizes, and last-observed time prominently; avoid a misleading percentage
when the number of undiscovered directories is unknown.

All filtering, counts, facets, samples, and pagination should query local SQL.
Changing processing steps or a filename filter must not walk the share again.
Avoid loading a million-row tree or all selection members into the browser.

## 2. Strengthen coverage, permissions, and recovery

Persist scan rules, a generation, source identity, directory task state, retry
count, lease owner/expiry, last error, and timestamps. Extend the existing schema
through an explicit versioned migration and backup; never reset evidence.

Record per-entry stat errors and per-directory listing errors separately.
Continue readable siblings. Distinguish denied, unavailable, changed during scan,
retryable failure, skipped by rule, and fully enumerated. A known name with
unavailable attributes retains unknown size/type/access fields. Do not convert
unknown size to zero or infer permission to read contents from successful stat.

Finalize absence only for a directory whose enumeration completed successfully
in the current generation. An unreadable branch, disconnect, changed root, or
interrupted attempt cannot mark its unseen descendants deleted. Keep historical
observations with explicit current accessibility/coverage state.

Pause/cancel cooperatively at batch boundaries; keep prior commits. Resume
unfinished tasks and retry chosen failed branches with bounded backoff. Root
identity changes require operator verification before rebinding to the dataset;
do not silently scan a different mount or discard the previous inventory.
Replaying a very large flat directory must remain idempotent. Do not assume an
OS directory-iterator offset remains valid across reconnects or restarts.

## 3. Add conservative parallel metadata I/O

Keep one coordinator and batched SQLite writer. Lease directory tasks to a
bounded I/O pool, with a bounded result queue and backpressure. Propose two
concurrent directory readers per source initially, configurable up to eight;
measure before increasing. Keep per-source limits so one share cannot monopolize
all workers. Tune metadata traversal separately from OCR/model concurrency.

Reuse `DirEntry` metadata; avoid repeated `realpath`, `stat`, and capability
probes for every entry. Discover names and directory candidates first, then
fetch additional attributes only where required. Record an unknown entry type
when determining it requires an unavailable metadata operation. Do not follow
symlink loops or cross unapproved mount boundaries.

More threads are not a hard timeout strategy. Python cannot cancel a future
that is already running, and a Linux hard NFS mount can retry requests
indefinitely. See [Python's executor cancellation contract](https://docs.python.org/3.12/library/concurrent.futures.html)
and [the NFS mount retry semantics](https://man7.org/linux/man-pages/man5/nfs.5.html).
For fault isolation, use supervised reader processes for risky shares, limit
replacement processes, trip a per-source circuit breaker, and expose stalled
operations. A kernel-blocked operation may still require share recovery or OS
intervention. Keep API/UI availability independent, and review mount behavior
with the platform administrator rather than changing mount options implicitly.

## 4. Freeze an Intake staging selection

Let users filter by root/folder, extension, name, dates, size, accessibility, and
prior processing. Support reproducible samples, a file cap, and a byte budget.
Show known and unknown byte totals separately. Start with a small sample, e.g.
100 files and at most 1 GiB of known logical bytes; unknown-size entries require
an explicit decision rather than silently bypassing the byte budget.

Persist membership as source ID, relative path, observed revision, and relevant
metadata, plus filter rules and scan generation. Confirm when coverage is partial.
A frozen selection must not silently grow as the scan discovers more files.
Persist the staging selection before enqueueing work; neither step requires
reading original contents.

Bridge this selection to the normal sidecar intake worker. The worker resolves
and checks access again, verifies current metadata/content identity, hashes only
selected files, and writes existing `.osii` artifacts and provenance. Record
changed, missing, denied, and failed files individually; continue the batch.
Successful files retain their work across interruption. Do not duplicate results
in a second library or implicitly migrate existing inventory-only extractions.

Move remaining expensive run-creation work (whole-selection hashing and folder
artifact construction) into durable worker phases as part of this bridge.
Queue acknowledgement should be fast. Track discovery, staging, content reads,
extraction, enrichment, and embedding separately. Model calls remain explicit;
metadata discovery never spends a model budget.

## 5. Validate before a 35 TB rollout

Implement permission/error granularity and the Intake bridge before enabling
parallel traversal by default. Then benchmark one, two, four, and eight readers
on approved representative branches. Measure metadata operations/sec, directory
and stat latency, API response time, queue depth, memory, database growth, and
share/server load. Prior million-row synthetic tests are useful SQL baselines,
not evidence of NFS throughput or mixed-permission correctness.

Required regression and fault checks:

- No source opens/hashes/model calls in discovery or staging previews.
- Per-file and per-directory permission failures; accessible siblings continue.
- Mid-enumeration disconnect, renamed/replaced directories, changed mounts,
  symlink races, stale leases, worker termination, and application restart.
- Disk-full rollback preserves earlier batches and canonical extraction data.
- Cancel, resume, and retry preserve frozen selection membership and outcomes.
- No false deletion after partial enumeration; safe replay of large directories.
- Million-entry paging/filtering with bounded API, browser, queue, and worker memory.
- A stalled share cannot freeze health checks or cause an unbounded retry/process storm.

Pilot a narrow branch, then several mixed-permission branches, then a scheduled
larger scan with operator-approved concurrency. Keep periodic delta scans and
retention policies explicit; do not promise filesystem snapshots or per-user ACL
mirroring in OSII-local's cached inventory.
