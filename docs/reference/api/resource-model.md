# API resource model

## Purpose

This document defines the conceptual resource model behind the AI-Ready-Ingest backend API.

It clarifies the distinction between canonical corpus artifacts, derived artifacts, curated overlays, and retrieval infrastructure.

## Canonical hierarchy

The backend reflects a composable OSII hierarchy rather than a flattened document store.

### Root-level artifacts

- `root.toml`
- `root.overview.toml`
- `root.synth.txt`

### Folder-level artifacts

- `folder-<folder_id>.toml`
- `folder-<folder_id>.overview.toml`
- `folder-<folder_id>.synth.toml`
- `folder-<folder_id>.synth.txt`

### Object-level artifacts

- `objects/<file_id>/meta.toml`
- `objects/<file_id>/manifest.jsonl`
- `objects/<file_id>/text.txt`
- `objects/<file_id>/artifacts/`
- `objects/<file_id>/synth.toml`
- `objects/<file_id>/synth.txt`

## Stable identifiers

The API prefers stable identifiers for canonical access:

- `file_id`
- `folder_id`
- `collection_id`
- `run_id`
- `job_id`

Where relevant, source-relative paths are exposed as canonical relpaths rooted at the shared data root.

## Scope model

The API uses scopes to represent corpus regions or curated subsets.

Supported scope types are:

- `root`
- `folder`
- `collection`
- `object`

### Root scope

Represents the full canonical corpus.

### Folder scope

Represents a folder subtree in the canonical hierarchy.

Folder scopes are subtree-based for filtering and search semantics.

### Collection scope

Represents a curated set of objects maintained outside the canonical OSII hierarchy.

### Object scope

Represents exactly one canonical object identified by `file_id`.

## Objects

An object is the canonical backend bundle for one ingested source file.

An object is identified by `file_id` and may expose:

- source metadata
- canonical extracted text
- manifest records
- image artifacts
- syntheses
- enrichment summaries
- collection membership references
- processing provenance

## Canonical text

Canonical extracted object text is stored at:

```text
objects/<file_id>/text.txt
```

This is the canonical backing text for grounded span access.

Downstream consumers should treat this as the canonical object text source unless a route explicitly defines some other preferred representation for convenience.

## Text representations

An object may expose multiple text representations.

Current examples include:

- `canonical`, with kind `canonical_extracted_text`
- `editable`, with kind `editable_text`

The preferred text endpoint provides the backend-selected text representation for common consumers, but canonical span grounding remains based on canonical object text.

## Manifest records

Manifest records are canonical structured extraction records stored in:

```text
objects/<file_id>/manifest.jsonl
```

Manifest records may include text-bearing records with:

- stable segment identifiers
- `span.char_start`
- `span.char_end`
- provenance such as `source_origin`

These are canonical extraction units.

## Text spans

Text-span endpoints provide canonical grounding over canonical object text using character offsets:

- `char_start`
- `char_end`

This is distinct from both:

- manifest segment identifiers
- derived search chunk identifiers

Canonical span reads operate over `objects/<file_id>/text.txt`.

## Syntheses

Syntheses are derived summaries or structured descriptions associated with canonical resources.

Current object synthesis outputs commonly include:

- `synth.txt`
- `synth.toml`

Syntheses are useful for downstream summarization and browsing, but they are not the canonical extracted text source.

## Collections

Collections are curated canonical overlays stored alongside other OSII artifacts.

Collections:

- are not canonical hierarchy nodes
- are stored as inspectable `collection.toml` and `members.jsonl` files
- should reference stable object identifiers such as `file_id`
- must survive extraction reruns, synthesis reruns, and embedding rebuilds

Typical storage location:

```text
.\osii-data\.osii\collections\<collection-id>\collection.toml
```

The rebuildable `state/catalog.sqlite3` indexes them for fast reads but is not
authoritative.

## Enrichments

Enrichments are optional derived outputs associated with scopes or objects.

Current examples include:

- keyword extraction outputs
- optional grounded Wiki Markdown returned by a conforming enricher for any
  supported scope
- structured tables, entity lists, and knowledge graphs returned by conforming
  enrichers
- future analytical outputs

Enrichments are:

- derived
- durable on disk
- rebuildable
- optional

Enrichments are not:

- canonical extraction text
- canonical object artifacts
- generic file serving surfaces

## Embeddings and retrieval chunks

The embeddings layer is derived and rebuildable.

Typical current layout:

```text
embeddings/
  segments.faiss
  segments.mapping.jsonl
  segments.meta.toml
```

Chunk mappings record method, requested size and overlap, exact text offsets,
previous/next chunk IDs, actual overlap, extraction identity, and source
segment/page grounding. BM25 and vector retrieval consume the same manifest.

Retrieval chunks are derived infrastructure for search ranking.

They are not canonical extraction units.

## Canonical versus derived summary

### Canonical

- object identity via `file_id`
- canonical object text in `objects/<file_id>/text.txt`
- manifest records in `objects/<file_id>/manifest.jsonl`
- canonical hierarchy concepts such as root and folders

### Derived but durable

- syntheses
- enrichments
- embeddings metadata and index files

### Curated overlays

- collections
- collection membership

### Retrieval infrastructure

- FAISS identifiers
- embedding chunks
- chunk identifiers

Downstream consumers should navigate and ground interactions using canonical identifiers and canonical text spans, not retrieval-only identifiers.


## Editable products and revisions

Saved summary text and JSON enrichment products share a revision API:

| Route | Request / result |
| --- | --- |
| `POST /api/products/list` | Scope object → `products` with family, filename, title, artifact type |
| `POST /api/products/revisions` | `{scope, family, filename}` → current revision ID, data, revisions, input state, library ID |
| `PUT /api/products/revisions` | Address + `expected_revision` + `data` to edit, or `revision` to restore |

`family` defaults to `enrichment` (a JSON, `.txt`, or `.md` filename, including a
relative name inside a legacy bundle); `synthesis` selects a
summary: `filename: "current"` for document/folder/library or a named `.txt`
variant for any scope, including collections. Paths must remain inside the scope’s
enrichment directory; traversal, hidden files, and internal `.meta.json` files are
rejected. Summary/text data is
`{artifact_type: "text", title: "Summary", text: "..."}`. Markdown files use the existing `wiki_markdown` wrapper and retain their raw
`.md` compatibility view. Standard structured
JSON products retain their artifact type and validate against the SDK schema.
Writes use compare-and-swap; a stale expected revision returns `409`, invalid
values return `400`. An edited product is limited to 5,000,000 serialized
characters. Revisions retain original outputs and lineage. Regeneration after a
human edit saves a candidate; restoring a revision is an explicit human choice.
The existing `/api/enrichments/revisions` routes, including wiki `markdown`
writes, remain compatible. No source file is rewritten by product edits.

A portable `.history/<product-hash>/manifest.json` stores complete revisions and
the active pointer atomically. JSON/summary files remain compatibility views.
A worker restart can repair a lagging view; a new, external sidecar edit is
retained as a human revision. Edits are interpretation, not proof that old
citation spans still support every changed passage.

### Document metadata

Synthesis returns `metadata.document_metadata` using the shared SDK
`DocumentMetadata` schema version 1. It contains nullable suggestions for
`descriptive_title`, `title`, `author`, `date`, `agency`, and `document_type`.
Each has `value`, optional `qualifier`, and optional exact-quote `evidence`.
A descriptive title labels content; title records the printed/source title.
Neither needs to equal the filename or each other. Blank means unknown.
New fields are optional for older schema-1 clients. See the [synthesis
spec](../processor-api/synthesis.md#suggested-document-metadata-and-long-inputs).

`GET /api/objects/{file_id}/metadata` returns `{file_id, revision,
document_metadata}`. Revision is null until a human overlay exists; the record
otherwise comes from current synthesis suggestions or is null.

`PUT /api/objects/{file_id}/metadata` accepts:

```json
{
  "expected_revision": null,
  "values": {
    "descriptive_title": "Thermal drift experiment",
    "title": "Report 123",
    "author": "",
    "date": "",
    "agency": "National laboratory",
    "document_type": "Technical report"
  }
}
```

This replaces the six human fields (omitted fields become unknown); values are
strings up to 240 characters or null. First edit requires explicit null, later
edits require the returned revision. Missing document is `404`, stale write
`409`, invalid input `400`. The overlay is stored as
`enrichments/document_metadata--manual.json` with `method: "human"`; it takes
precedence for display without changing filesystem metadata or the AI record.
Display title prefers descriptive title, then source title, then filename.
