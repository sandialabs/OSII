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

### Objects

- `GET /api/objects/{file_id}`
- `GET /api/objects/{file_id}/manifest`
- `GET /api/objects/{file_id}/texts`
- `GET /api/objects/{file_id}/texts/preferred`
- `GET /api/objects/{file_id}/syntheses`

### Text spans

- `GET /api/text/objects/{file_id}/span`
- `GET /api/text/objects/{file_id}/span/context`

### Enrichments

- `POST /api/enrichments/list`
- `GET /api/enrichments/objects/{file_id}/{filename}`

### Search

- `GET /api/search`

### Ingestion and derived-data workflows

- `GET /api/intake/readiness`
- `GET /api/browse`
- `POST /api/resolve`
- `GET /api/extractors`
- `GET /api/synthesizers`
- `GET /api/folder-synthesizers`
- `POST /api/runs`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/logs`
- `POST /api/embeddings/build`
- `GET /api/embeddings/build/{job_id}`
- `GET /api/embeddings/meta`

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

## Object resources

Object resources provide the preferred read surface for canonical object metadata, text access, syntheses, and related summaries.

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
- `POST /api/resolve`
- `GET /api/extractors`
- `GET /api/synthesizers`
- `GET /api/folder-synthesizers`
- `POST /api/runs`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/logs`
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
