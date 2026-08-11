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
- grounded LLM wiki Markdown for document and collection scopes
- model-free wiki artifact templates
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
