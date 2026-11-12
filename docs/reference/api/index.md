# OSII API overview

## Purpose

This document provides a practical overview of the current AI-Ready-Ingest backend API.

It is intended for developers and downstream consumers who need to:

- discover backend capabilities
- inspect canonical corpus resources
- manage curated collections
- access grounded text spans
- retrieve derived enrichments
- perform search over extracted content
- run ingestion and embedding workflows

This overview is descriptive and implementation-aligned. Exact request and response schemas should be defined in `openapi.yaml`.

## API direction

The backend API is resource-oriented and centered on core backend capabilities.

User-facing dashboard rendering does not live in this repository.

Downstream consumers should use:

- scope resources
- collection resources
- object resources
- text-span resources
- enrichment resources
- search resources

Compatibility read routes under `/api/osii/...` still exist, but new integrations should prefer the newer resource-oriented route families.

## Base assumptions

These filesystem locations describe the default sidecar backend. The optional
[local PostgreSQL composition](../local-storage.md) preserves the Workbench route
families but saves library records and processing jobs in PostgreSQL. Runtime
reports `storage_backend`; initialization/import remain explicit CLI commands.
This is still the standalone API without hosted login, not an authentication bypass.

By default the application commonly runs on:

```text
http://localhost:8511
```

The OSII store is typically located at:

```text
.\osii-data\.osii
```

The shared data root is typically:

```text
.\osii-data\source
```

Canonical collection metadata is stored inside the OSII store, typically at:

```text
.\osii-data\.osii\collections\<collection-id>\collection.toml
```

The disposable `.osii\state\catalog.sqlite3` database accelerates API reads and
can always be rebuilt from canonical files.

Collection metadata must survive:

- extraction reruns
- synthesis reruns
- embedding rebuilds

Collection membership must reference stable object identifiers such as `file_id`, not only transient filesystem paths.

## Core endpoint families

### Scopes

- `GET /api/scopes/root`
- `GET /api/scopes/folders`
- `GET /api/scopes/collections`
- `POST /api/scopes/describe`

### Collections

- `GET /api/collections`
- `POST /api/collections`
- `GET /api/collections/{collection_id}`
- `PATCH /api/collections/{collection_id}`
- `DELETE /api/collections/{collection_id}`
- `GET /api/collections/{collection_id}/members`
- `POST /api/collections/{collection_id}/members`
- `DELETE /api/collections/{collection_id}/members/{file_id}`
- `GET /api/collections/{collection_id}/export`
- `POST /api/packages/import`

### Objects

- `GET /api/objects/{file_id}`
- `GET /api/objects/{file_id}/manifest`
- `GET /api/objects/{file_id}/extractions/{variant_id}/artifacts`
- `GET /api/objects/{file_id}/texts`
- `GET /api/objects/{file_id}/texts/preferred`
- `GET /api/objects/{file_id}/syntheses`
- `GET /api/objects/{file_id}/governance`
- `PUT /api/objects/{file_id}/governance`
- `POST /api/objects/{file_id}/deletion-preview`
- `DELETE /api/objects/{file_id}`

The extraction-artifact endpoint lists safe previews of non-text products
returned by one extractor version. Standard tables are rendered generically by
the dashboard; large or binary artifacts remain listed without being embedded
in the JSON response.

### Text spans

- `GET /api/text/objects/{file_id}/span`
- `GET /api/text/objects/{file_id}/span/context`

### Enrichments

- `POST /api/enrichments/list`
- `POST /api/enrichments/payload`
- `DELETE /api/enrichments/payload`
- `GET /api/enrichments/objects/{file_id}/{filename}`

### Search

- `GET /api/search`

### Ingestion and derived-data workflows

- `GET /api/intake/readiness`
- `GET /api/browse`
- `GET /api/browse/roots` (navigation shortcuts without directory enumeration)
- `GET /api/browse/page?path=...&limit=100` (isolated, nonrecursive directory page)
- `GET /api/browse/page?cursor=...&limit=100` (continue the same directory iterator)
- `DELETE /api/browse/page/{cursor}` (release a browser cursor)
- `POST /api/resolve`
- `GET /api/extractors`
- `GET /api/synthesizers`
- `GET /api/folder-synthesizers`
- `POST /api/runs`
- `GET /api/runs` (run history, durable queue state, and worker heartbeat)
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/logs`
- `POST /api/runs/{run_id}/{pause|resume|cancel|retry}`
- `POST /api/runs/recover` safely requeues only work whose worker lease expired
- `POST /api/embeddings/build`
- `GET /api/embeddings/build/{job_id}`
- `GET /api/embeddings/meta`

`POST /api/resolve` supplies the detailed processing plan for Intake review.
`POST /api/runs` queues the selected paths with a lightweight preview instead
of rereading every original to repeat that plan. The worker owns content hashes
and extraction; slow source-folder access during queueing does not block API
health or Queue & activity requests. Completed Intake/library runs with failed
or partially processed files also accept `retry`: successful files stay complete,
failed files return to pending, and the same durable job is requeued. Successful
extraction versions on partial files are retained when their content identity
still matches. Recovered files are included when embedding membership is rebuilt;
existing chunk/vector checkpoints are preserved. Retrying an
embedding failure retains its existing embedding-only behavior. Fully successful
and cancelled runs remain terminal.

### Bounded file discovery and selection

The new directory browser leaves legacy `GET /api/browse` behavior unchanged.
Pages return `current_path`, `parent_path`, `entries`, `has_more`, and an opaque
`cursor` (null when exhausted). Entries have `name`, `path`, `type`,
`size_bytes`, and an optional access `error`; unavailable entries and symbolic
links are not selectable. `limit` is 1–200 inspected entries, including hidden
entries, so an empty page may still have a continuation cursor. Pages use native
directory order, not a global sort. No catalog scan, recursion, or content read
occurs. Cursors are ephemeral, expire after 45 seconds idle, and are not stable
snapshots of a changing directory. `410` requests reopening an expired cursor;
`503` reports a timeout/cancelled read. Disconnecting an in-flight request or
explicitly deleting its cursor stops its isolated reader. Eight browsers may be
open at once; a new request is rejected rather than evicting another user's cursor.
A kernel-blocked filesystem call can still need OS/mount recovery.

`POST /api/volume/selections` retains filter-based selection and adds optional
`entry_ids` (1–10,000 IDs). Explicit selection requires `filters.source_id`, cannot
use sampling, and must fit the requested file/byte limits. Every distinct ID must
be eligible and observed in the latest scan of that source; otherwise the request
fails atomically with `422`. Unknown IDs, wrong-source IDs, and unavailable files
are not silently dropped. Unfinished discovery requires `allow_partial: true`.
Successful selections remain immutable as discovery continues.

`GET /api/volume/runs` retains its default ascending cursor contract. Optional
`recent=true` returns descending IDs, `before=<id>` loads older history, and
`active_only=true` restricts results to queued/running/paused work. `kind=scan`
(or a processing stage) filters jobs before pagination. Scan IDs belong
to the inventory API; they are not interchangeable with Core processing run IDs.
Scan responses include `issue_code: "identity_changed"` when a failed directory
identified a different registered root, allowing contextual recovery without a
filesystem probe during status polling.

### Setup and local administration

- `GET /api/admin/setup` returns the human-facing readiness summary, selected
  methods, provider presence, and capability-service state.
- `PUT /api/admin/model-providers/{provider_id}/credential` accepts an API key
  as a write-only value when local `.env` writes are enabled.
- `DELETE /api/admin/model-providers/{provider_id}/credential` forgets a key
  previously saved by OSII.
- `GET /api/admin/services` lists allowlisted capability services.
- `POST /api/admin/services/{service_id}/{start|stop|restart}` controls only a
  service owned by the local launcher.
- `GET /api/admin/services/{service_id}/logs` returns a bounded recent log tail.

Credential responses report presence and source but never return the value.
The service-control endpoints return `503` in deployments without the local
loopback supervisor.

### Compatibility and artifact serving

- compatibility read routes under `/api/osii/...`
- `GET /artifact/{file_path:path}`

## General conventions

### Stable identifiers

The API prefers stable identifiers in canonical read paths:

- `file_id`
- `folder_id`
- `collection_id`
- `run_id`
- `job_id`

### Relative path conventions

Where relevant, source-relative paths are exposed as canonical relpaths rooted at the shared data root, for example:

```text
reports/FY26/Q2_Status_Report.pdf
```

### Canonical versus derived data

Downstream consumers should distinguish between:

- canonical stored artifacts, such as object text and manifest spans
- derived artifacts, such as enrichments and syntheses
- retrieval/index artifacts, such as embedding chunks and FAISS identifiers

The resource model and search semantics documents define these distinctions more precisely.

## Scope resources

Scope resources provide a uniform way to describe root, folder, collection, and object scopes.

### Root scope

```http
GET /api/scopes/root
```

Example response:

```json
{
  "scope": {
    "scope_type": "root",
    "scope_id": "root",
    "label": "root"
  },
  "member_file_ids": [
    "sha256-test123"
  ]
}
```

### Folder scope catalog

```http
GET /api/scopes/folders
```

This returns a flat catalog of folder scope descriptors.

Example response:

```json
{
  "scopes": [
    {
      "scope_type": "folder",
      "scope_id": "folder-root",
      "folder_id": "folder-root",
      "path": "",
      "label": "root-folder"
    }
  ]
}
```

### Collection scope catalog

```http
GET /api/scopes/collections
```

This returns collection scope descriptors, not full collection resources.

Example response:

```json
{
  "scopes": [
    {
      "scope_type": "collection",
      "scope_id": "col-abc123def456",
      "collection_id": "col-abc123def456",
      "label": "sensor-calibration-review",
      "kind": "file-list",
      "description": "Documents related to calibration methods and drift analysis.",
      "document_count": 2
    }
  ]
}
```

### Describe a scope

```http
POST /api/scopes/describe
Content-Type: application/json
```

Supported request variants:

- root
- folder by `folder_id`
- collection by `collection_id`
- object by `file_id`

Example request:

```json
{
  "scope_type": "collection",
  "collection_id": "col-abc123def456"
}
```

Example response:

```json
{
  "scope": {
    "scope_type": "collection",
    "scope_id": "col-abc123def456",
    "collection_id": "col-abc123def456",
    "label": "sensor-calibration-review"
  },
  "member_file_ids": [
    "sha256-test123"
  ]
}
```

Folder scope behavior is subtree-based for filtering and search semantics.

## Collection resources

Collections are curated groupings of documents. They are not canonical OSII hierarchy nodes.

### List collections

```http
GET /api/collections
```

Example response:

```json
{
  "collections": [
    {
      "id": "col-abc123def456",
      "name": "sensor-calibration-review",
      "description": "Documents related to calibration methods and drift analysis.",
      "kind": "file-list",
      "color": "#3366ff",
      "document_count": 2,
      "created_utc": "2026-06-18T12:00:00Z",
      "updated_utc": "2026-06-18T12:05:00Z"
    }
  ]
}
```

### Create a collection

```http
POST /api/collections
Content-Type: application/json
```

Required fields:

- `name`

Optional fields:

- `description`
- `kind`
- `color`

Example request:

```json
{
  "name": "sensor-calibration-review",
  "description": "Documents related to calibration methods and drift analysis.",
  "kind": "file-list",
  "color": "#3366ff"
}
```

Example response:

```json
{
  "collection": {
    "id": "col-abc123def456",
    "name": "sensor-calibration-review",
    "description": "Documents related to calibration methods and drift analysis.",
    "kind": "file-list",
    "color": "#3366ff",
    "document_count": 0,
    "created_utc": "2026-06-18T12:00:00Z",
    "updated_utc": "2026-06-18T12:00:00Z"
  }
}
```

### Update a collection

```http
PATCH /api/collections/{collection_id}
Content-Type: application/json
```

Writable fields:

- `name`
- `description`
- `kind`
- `color`

Example request:

```json
{
  "description": "Updated description",
  "kind": "manual"
}
```

### Read one collection

```http
GET /api/collections/{collection_id}
```

### Delete one collection

```http
DELETE /api/collections/{collection_id}
```

### Read collection membership

```http
GET /api/collections/{collection_id}/members
```

Example response:

```json
{
  "collection": {
    "id": "col-abc123def456",
    "name": "sensor-calibration-review",
    "description": "Documents related to calibration methods and drift analysis.",
    "kind": "file-list",
    "color": "#3366ff",
    "document_count": 2,
    "created_utc": "2026-06-18T12:00:00Z",
    "updated_utc": "2026-06-18T12:05:00Z"
  },
  "file_ids": [
    "sha256-test123"
  ]
}
```

### Add members to a collection

```http
POST /api/collections/{collection_id}/members
Content-Type: application/json
```

Membership addition is batch-oriented and effectively idempotent.

### Remove a member from a collection

```http
DELETE /api/collections/{collection_id}/members/{file_id}
```

Removal is success/no-op style. If the collection exists but the document is not currently a member, the response reports `removed: false` rather than treating that case as an error.

### Export and import an OSII package

```http
GET /api/collections/{collection_id}/export
POST /api/packages/import
```

Export returns a ZIP containing collection and object sidecars plus a versioned
`osii-package.json` checksum manifest; it never includes source files. Import
uses multipart field `package`, validates every member before writing, merges
objects by immutable `file_id`, unions governance labels, and invalidates
corpus-wide derived indexes. See [sensitive data and transfer](../../operations/sensitive-data.md).

## Object resources

Object resources provide the preferred read surface for canonical object metadata, text access, syntheses, and related summaries.

### Read or update governance metadata

```http
GET /api/objects/{file_id}/governance
PUT /api/objects/{file_id}/governance
```

The JSON fields are `sensitivity_labels`, `tags`, and `handling_notes`. They are
stored canonically in `objects/<file_id>/governance.toml` and communicate
awareness; they do not enforce access control.

### Preview and delete one object

```http
POST /api/objects/{file_id}/deletion-preview
DELETE /api/objects/{file_id}
```

Preview accepts mode `sidecar_only` or `source_and_sidecar`. Delete requires the
same mode, the returned `preview_token`, and `confirmation` exactly equal to the
file ID. Active Intake jobs or a stale preview block deletion.

### Read object aggregate

```http
GET /api/objects/{file_id}
```

Example response:

```json
{
  "file_id": "sha256-test123",
  "meta": {
    "file": {
      "source_relpath": "reports/example.pdf",
      "filename": "example.pdf",
      "mime": "application/pdf",
      "size_bytes": 1234,
      "mtime_utc": "2026-05-21T00:00:00Z"
    },
    "hash": {
      "sha256": "test123"
    }
  },
  "overview": {
    "file_id": "sha256-test123",
    "meta": {
      "file": {
        "source_relpath": "reports/example.pdf",
        "filename": "example.pdf",
        "mime": "application/pdf",
        "size_bytes": 1234,
        "mtime_utc": "2026-05-21T00:00:00Z"
      },
      "hash": {
        "sha256": "test123"
      }
    },
    "text_count": 1,
    "image_count": 0,
    "has_synth": true,
    "text_items": [
      {
        "kind": "text",
        "id": "seg-000001",
        "path": "text.txt",
        "type": "page",
        "span": {
          "char_start": 0,
          "char_end": 38
        },
        "source_origin": {
          "source_type": "pdf",
          "unit_type": "page",
          "page": 1
        },
        "related_ids": []
      }
    ],
    "image_items": []
  },
  "collections": [
    {
      "id": "col-abc123def456",
      "name": "sensor-calibration-review",
      "kind": "file-list"
    }
  ],
  "processing": {
    "extractor": {
      "name": null,
      "display_name": null
    },
    "synthesizer": {
      "name": null,
      "display_name": null
    },
    "canonical_text_path": "objects/sha256-test123/text.txt",
    "editable_text_path": null,
    "has_editable_text": false,
    "capabilities": {
      "supports_markdown_render": false
    }
  },
  "enrichments": [
    {
      "name": "keywords--stats_keywords.json",
      "kind": "file",
      "relpath": "objects/sha256-test123/enrichments/keywords--stats_keywords.json"
    }
  ]
}
```

### Read object manifest

```http
GET /api/objects/{file_id}/manifest
```

Example response:

```json
{
  "file_id": "sha256-test123",
  "records": [
    {
      "kind": "text",
      "id": "seg-000001",
      "path": "text.txt",
      "type": "page",
      "span": {
        "char_start": 0,
        "char_end": 38
      },
      "source_origin": {
        "source_type": "pdf",
        "unit_type": "page",
        "page": 1
      },
      "related_ids": []
    }
  ]
}
```

### List object text representations and canonical segments

```http
GET /api/objects/{file_id}/texts
```

Example response:

```json
{
  "file_id": "sha256-test123",
  "representations": [
    {
      "name": "canonical",
      "kind": "canonical_extracted_text",
      "path": "objects/sha256-test123/text.txt",
      "exists": true,
      "preferred": true
    },
    {
      "name": "editable",
      "kind": "editable_text",
      "path": "objects/sha256-test123/editable_text.txt",
      "exists": false,
      "preferred": false
    }
  ],
  "segments": [
    {
      "kind": "text",
      "id": "seg-000001",
      "path": "text.txt",
      "type": "page",
      "span": {
        "char_start": 0,
        "char_end": 38
      },
      "source_origin": {
        "source_type": "pdf",
        "unit_type": "page",
        "page": 1
      },
      "related_ids": []
    }
  ]
}
```

### Read preferred text representation

```http
GET /api/objects/{file_id}/texts/preferred
```

Example response:

```json
{
  "file_id": "sha256-test123",
  "representation": "canonical",
  "kind": "canonical_extracted_text",
  "text": "Thermal calibration drift was reduced.",
  "path": "objects/sha256-test123/text.txt"
}
```

If editable text exists, it may become the preferred representation.

### Read available syntheses

```http
GET /api/objects/{file_id}/syntheses
```

Example response:

```json
{
  "file_id": "sha256-test123",
  "current_text": "This appears to be a technical report about thermal calibration drift.",
  "current_toml": {
    "path": {
      "source_relpath": "reports/example.pdf"
    },
    "synthesis": {
      "synthesis": "Technical report about thermal calibration drift.",
      "doc_type": "technical report",
      "quality": "default"
    },
    "details": {
      "description": "This appears to be a technical report about thermal calibration drift."
    }
  },
  "syntheses": [
    {
      "name": "current",
      "text_path": "C:\\...\\.osii\\objects\\sha256-test123\\synth.txt",
      "toml_path": "C:\\...\\.osii\\objects\\sha256-test123\\synth.toml",
      "scope": "object"
    }
  ]
}
```

## Text-span resources

Text-span routes provide canonical grounding over object text stored in:

```text
objects/<file_id>/text.txt
```

### Read a canonical text span

```http
GET /api/text/objects/{file_id}/span?char_start=0&char_end=10
```

Example response:

```json
{
  "file_id": "sha256-test123",
  "char_start": 0,
  "char_end": 10,
  "text": "Thermal ca"
}
```

Notes:

- `char_start` and `char_end` are required query parameters
- `char_end` is effectively exclusive
- spans are validated against canonical object text
- current invalid-range behavior returns a JSON error body with HTTP 200 rather than strict `400` or `404`

### Read span context

```http
GET /api/text/objects/{file_id}/span/context?char_start=0&char_end=10&context_chars=5
```

Example response:

```json
{
  "file_id": "sha256-test123",
  "char_start": 0,
  "char_end": 10,
  "match_text": "Thermal ca",
  "before_text": "",
  "after_text": "librat",
  "window_start": 0,
  "window_end": 15
}
```

`context_chars` is optional and currently defaults to `200`.

## Enrichment resources

Enrichments are optional, derived, durable-on-disk outputs associated with scopes or objects.

They are not canonical extraction artifacts.

### List enrichments for a scope

```http
POST /api/enrichments/list
Content-Type: application/json
```

Supported request variants:

- root
- folder
- collection
- object

Example request:

```json
{
  "scope_type": "object",
  "file_id": "sha256-test123"
}
```

Example response:

```json
{
  "scope": {
    "scope_type": "object",
    "file_id": "sha256-test123"
  },
  "enrichments": [
    {
      "name": "keywords--stats_keywords.json",
      "kind": "file",
      "relpath": "objects/sha256-test123/enrichments/keywords--stats_keywords.json"
    }
  ]
}
```

### Read or delete a scope enrichment payload

Scope-level JSON artifacts are read with `POST /api/enrichments/payload` and a
body containing `scope` plus a path-free `filename`. The same payload sent with
`DELETE` removes that derived JSON artifact and its `.meta.json` sidecar. A
missing artifact returns `404`; an invalid scope or filename returns `400`.
This never deletes source files, extracted text, or collection membership. The
dashboard uses it for the confirmed **Delete saved wiki** action.

### Read an object enrichment payload

```http
GET /api/enrichments/objects/{file_id}/{filename}
```

This currently returns JSON-wrapped object enrichment payloads rather than arbitrary raw bytes.

Example response:

```json
{
  "file_id": "sha256-test123",
  "filename": "keywords--stats_keywords.json",
  "relpath": "objects/sha256-test123/enrichments/keywords--stats_keywords.json",
  "data": {
    "keywords": [
      {
        "term": "thermal",
        "count": 1
      }
    ],
    "input_object_count": 1
  }
}
```

## Search

### Public search route

```http
GET /api/search?q=thermal calibration drift&top_k=5
```

Example response:

```json
{
  "query": "thermal calibration drift",
  "top_k": 5,
  "results": [
    {
      "faiss_id": 0,
      "chunk_id": "chunk-sha256-test123-000001",
      "file_id": "sha256-test123",
      "source_relpath": "reports/example.pdf",
      "chunk_method": "paragraph",
      "chunk_index": 1,
      "char_start": 0,
      "char_end": 38,
      "source_text_representation": "canonical",
      "source_text_kind": "canonical_extracted_text",
      "truncated": false,
      "score": 0.8123
    }
  ]
}
```

The current public route is a simple semantic search endpoint.

Richer scope-aware search behavior exists in backend service logic, but should not be treated as public route behavior unless and until it is exposed as a formal route.

## Search result semantics

Search results may be ranked using derived embedding chunks.

They should be interpreted as retrieval results with canonical grounding information, not as canonical extraction segment identifiers.

Downstream consumers should use returned object identity and text-span grounding fields for navigation and text interaction.

In particular:

- `faiss_id` is an internal retrieval identifier
- `chunk_id` identifies a derived retrieval chunk, not a canonical manifest segment
- `file_id`, `char_start`, and `char_end` are the grounding fields relevant for canonical text interaction

## Discovery and workflow endpoints

The backend also exposes discovery and orchestration routes for extraction, synthesis, run control, and embeddings.

These include:

- `GET /api/intake/readiness`
- `GET /api/browse`
- `GET /api/browse/roots` (navigation shortcuts without directory enumeration)
- `GET /api/browse/page?path=...&limit=100` (isolated, nonrecursive directory page)
- `GET /api/browse/page?cursor=...&limit=100` (continue the same directory iterator)
- `DELETE /api/browse/page/{cursor}` (release a browser cursor)
- `POST /api/resolve`
- `GET /api/extractors`
- `GET /api/synthesizers`
- `GET /api/folder-synthesizers`
- `POST /api/runs`
- `GET /api/runs`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/logs`
- `POST /api/runs/{run_id}/{pause|resume|cancel|retry}`
- `POST /api/runs/recover`
- `POST /api/embeddings/build`
- `GET /api/embeddings/build/{job_id}`
- `GET /api/embeddings/meta`

The existing implementation-aligned examples for these routes may be retained, with one update:

- embeddings metadata should mention chunking method and chunk manifest as part of current implementation detail

## Artifact serving

### Serve an OSII-relative artifact

```http
GET /artifact/{file_path:path}
```

Example:

```text
/artifact/objects/sha256-.../artifacts/artifact-000001.png
```

This route serves OSII-relative artifact paths only.

It is not arbitrary filesystem serving, and path traversal protections are enforced.

## Compatibility

Compatibility read routes under `/api/osii/...` are still implemented.

New consumers should prefer:

- `/api/scopes/...`
- `/api/collections/...`
- `/api/objects/...`
- `/api/text/...`
- `/api/enrichments/...`

Removed route families include:

- `/api/dashboard/...`
- dashboard/workbench HTML routes

See `compatibility.md` for migration-oriented notes.

## Next step

Use this overview together with:

- `resource-model.md`
- `search-semantics.md`
- `compatibility.md`
- `openapi.yaml`

The Markdown documents explain behavior and conventions. The OpenAPI document should define exact schemas, parameters, and response contracts.


## Research reports

Open **Research reports** in Tools, select a collection or document, and describe
its audience, question, structure, and desired level of detail. The brief accepts
up to 60,000 characters. A configured chat model writes a Markdown report;
without one, OSII creates clearly labelled extractive research notes. An empty
scope prompts you to process its documents first.

Click any source marker to inspect the exact excerpt alongside the report.
**Open passage in document** opens its preserved text representation, page (when
known), and character range. Source identity includes a SHA-256 fingerprint of
the full extracted text; the document viewer checks that fingerprint when opening
a report reference and flags changed text. Bibliographic entries use available metadata and simple
title/year heuristics; they are best guesses and remain editable. Citation checks
verify reference identity and location, not the model's interpretation.

Use **Edit text** to change prose or bibliography details. **Make it better**
proposes a revision against the report's original scope and brief. Review the
removed and added lines, accept or reject individual changes, or choose
**Accept all**. Pending changes never enter the report or its exports. Editing
and new generation pause during review. **Undo / restore** restores the previous
draft after a generation or completed revision.

Drafts are retained in the current browser tab's session storage (separately per
hosted account), not saved as canonical library artifacts. Export `.md` for normal
Markdown or `.mmd` for LaTeX/Mathpix Markdown. Both preserve equations, clickable
absolute OSII links, bibliography, coverage warnings, and exact excerpt/fingerprint
notes. Document links require access to the same running OSII library; evidence
notes can be read without it. Mathpix rendering uses the existing local renderer;
no Mathpix account or external conversion is required.

`POST /api/research/report` accepts:

```json
{
  "scope": {"scope_type": "collection", "collection_id": "collection-id"},
  "prompt": "Compare the findings and discuss the limitations.",
  "format": "markdown"
}
```

For a revision, also send `current_markdown`, `improvement`, and the `sources`
returned with the report. Core re-reads those sources and ignores client-supplied
paths and links. A changed/deleted extraction or out-of-scope reference returns
409; an empty scope or invalid request returns 422; unusable model output or
unknown references returns 502. The hosted endpoint requires authentication,
collection visibility, CSRF protection, and the shared writing budget.

Reports currently sample the first 24 documents in source-path order, selecting
an introduction and a lexical prompt-matched passage per document (up to 1,400
characters each). Revisions retain previously verified excerpts, with a maximum
of 64 passages. This is bounded evidence sampling, not exhaustive literature
review. The response exposes `documents_in_scope`, `documents_sampled`, source
snapshots, writing provider/model, format, and coverage warnings. Narrow large
collections for fuller coverage. Core rechecks text fingerprints after writing
and rejects changed evidence rather than silently attaching stale locations.

### Extraction routing setup

`GET /api/extractor-routes` returns `routes` and the active `path` to
`tools.toml`. `PUT /api/extractor-routes` preserves other tool configuration and
validates primary and fallback file-type compatibility.

`POST /api/extractor-routes/import` accepts `{"toml": "..."}` (up to 1 MiB)
and returns `ok`, `routes`, `errors`, and `warnings`. It accepts
`[[routes.extractor]]` or legacy `[[routes]]` tables and never saves; clients
review the returned draft before using PUT.

Processor administration records expose `resolved_models` and `model_error`
for per-service model assignment. Missing bindings inherit enabled compatible
library defaults; explicit disabled or missing bindings report a setup error.

### Apache Tika toolbox configuration

Save the upstream address with `PUT /api/admin/processor-settings/tika` and
`{"config": {"tika_endpoint": "http://your-tika:9998", "chunk_chars": 4000}}`.
Both `tika` and `tika_catchall` intake routes use these saved settings. The
adapter exposes the standard `/v1/descriptor` and `/v1/extract` endpoints;
`/health` checks the wrapper and `/upstream-health?tika_endpoint=...` checks
Apache Tika. The normal development stack prepares and manages Apache Tika
automatically; `OSII_TIKA_MANAGED=false` selects an externally managed runtime. See the
[Apache Tika adapter guide](../extractor-routing.md#apache-tika-processor-module).
