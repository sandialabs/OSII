# ADR: Single-host canonical volume database

Status: accepted for the large-volume pilot, 5 November 2026.

## Context

OSII-local persists portable per-document sidecars and derives its SQLite catalog
from them. Its intake and reconciliation paths collect whole file lists and
compute content hashes during planning. The server edition uses PostgreSQL,
but its initial ingestion also sorts the entire tree and couples extraction
with embedding. Neither workflow provides cheap, resumable metadata discovery
over millions of files. Corporate hosted-service availability is uncertain;
standalone workstations and SSH-accessible nodes are available.

## Decision

Add a separate canonical volume database using SQLite on genuinely local disk.
Preserve OSII-local's store and commands. Use the existing host development
launcher to select the volume API and worker explicitly with
`OSII_STORAGE_MODE=volume`. A separate dashboard workflow consumes that API;
filesystem routes, the filesystem MCP adapter, and catalog rebuild behavior do
not access the volume store.

Inventory entries identify locations independently of content hashes. Discovery
streams metadata into bounded batches and persists directory work. Successful
directory enumeration establishes absence only within that directory. Read,
permission, root-identity, and enumeration failures leave coverage incomplete.
Selected processing establishes content identity and immutable extraction
records, preserving historical source-revision links. The known native parser
can reuse results across locations with matching content and format; arbitrary
processors include request metadata in their cache identity.

Core alone owns the database. One leased coordinator scans or processes at a
time; Processor API v1 services receive bounded explicit requests. Extraction,
OCR, synthesis, and enrichment commit separately. An embedded FTS5 index is
rebuildable from canonical text. Processor configurations are checked against
descriptor JSON Schemas without remote reference retrieval.

## Consequences

The pilot needs no database service, corporate hosting, distributed queue, or
mandatory sidecars. It needs an explicit schema version, transactional backup,
disk capacity for canonical text and artifacts, and a single owning host. WAL
is unsuitable for a database file shared across hosts over SMB/NFS.

The first implementation is one operator and one visibility group. Model-wide
processing, vectors, cross-document research, per-user share ACLs, and distributed
workers remain follow-up work. A future server implementation may reuse the
source/revision/job concepts without making SQLite a PostgreSQL fallback.

Operational details and recovery procedures are in
[large-volume operation](../operations/large-volumes.md).
