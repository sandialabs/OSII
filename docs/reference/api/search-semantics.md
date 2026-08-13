# API search semantics

## Purpose

This document clarifies the semantics of search results returned by the current backend search implementation.

It is especially important for consumers that need to present search results, navigate to source text, or support grounded text interaction.

## Current public route

The currently documented public route is:

```http
GET /api/search
```

Example:

```http
GET /api/search?q=thermal calibration drift&top_k=5
```

Representative response:

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
      "chunk_method": "sentence_window",
      "chunk_index": 1,
      "source_segment_ids": ["seg-000001"],
      "source_pages": [1],
      "overlap_with_previous": 0,
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

## Search result semantics

Search results may be ranked using derived embedding chunks.

They should be interpreted as retrieval results with canonical grounding information, not as canonical extraction segment identifiers.

Downstream consumers should use returned object identity and text-span grounding fields for navigation and text interaction.

## Important field interpretation

### Canonical grounding fields

These are the fields downstream consumers should use for grounded navigation:

- `file_id`
- `char_start`
- `char_end`

These point back to canonical object identity and canonical text offsets.

### Derived retrieval identifiers

These fields are retrieval-oriented and should not be treated as canonical document identifiers:

- `faiss_id`
- `chunk_id`
- `chunk_index`

These identify derived retrieval artifacts, not canonical extraction segments.

### Representation metadata

These fields describe which text representation was used as the source for the search hit:

- `source_text_representation`
- `source_text_kind`

Consumers should not assume that these fields redefine canonical grounding behavior.

## Distinguishing chunks, manifest segments, and spans

The backend distinguishes between three related but different concepts.

### Manifest text records

Manifest text records are canonical extraction records stored in the object manifest.

They may have stable segment identifiers such as `seg-000001` and provenance such as page information.

### Search chunks

Search chunks are derived retrieval units used for embedding and ranking.

The default uses sentence/paragraph-aligned overlapping windows. Paragraph and
fixed-window compatibility modes remain available.

They are not canonical extraction units.

### Text spans

Text spans are canonical grounded slices over object text, identified by:

- `file_id`
- `char_start`
- `char_end`

For canonical interaction, text spans are the most important grounding layer.

## Current limitations of the public route

The current public `GET /api/search` route:

- exposes `faiss_id`
- exposes `chunk_id`
- exposes `char_start` and `char_end`
- does not currently return `snippet`
- does not currently return `source_origin`
- does not currently return canonical manifest segment identifiers

Consumers that need richer rendering may need to resolve grounded spans separately using text-span routes.

The dashboard uses `POST /api/search`, which additionally resolves the source
manifest `segment_id`, PDF `page`, snippet, collections, and `source_origin`.
Its `source_origin` reports all source pages/segments touched by a chunk and the
actual overlap with the preceding chunk. Highly redundant overlapping results
are suppressed before the requested `top_k` is returned.

## Scope-aware search behavior

Richer scope-aware search behavior exists in backend service logic.

That richer behavior may support:

- scope filtering
- collection-aware results
- object-aware results
- richer display-oriented grounding

However, that behavior should not be documented as public route behavior unless and until it is exposed as a formal API route.

## Consumer guidance

When rendering search results:

1. treat the result as a retrieval hit, not a canonical segment record
2. use `file_id`, `char_start`, and `char_end` as the grounding coordinates
3. use object and text-span routes to retrieve canonical context as needed
4. do not depend on `faiss_id` stability
5. do not treat `chunk_id` as a stable canonical identifier

## Dashboard history and suggestions

The dashboard's recent searches are convenience state, not an API or canonical
OSII artifact. It stores at most 20 entries under the versioned browser key
`osii.activity-history.v1`. A search entry contains only the query, timestamp,
scope identifiers, and requested mode. Repeating an identical query in the
same scope moves it to the top with the newest requested mode. Users can remove
one entry or clear the list.

Chat prompts use the same browser-local store and limit but never store model
answers, citations, providers, or retrieved text. Selecting an old prompt only
prefills the input; it never sends a request automatically. If browser storage
is disabled or corrupt, Search and Chat behave normally with empty history.

Scope suggestions come from the canonical
`keywords--noun_adjective_ngrams.json` enrichment. The dashboard reads up to
six ranked phrases and launches hybrid search in the same root or collection
scope. BM25 remains the backend fallback when semantic retrieval is
unavailable. No history or suggestion state is exported with `.osii`.
