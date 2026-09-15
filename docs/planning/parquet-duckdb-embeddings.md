# Future design note: Parquet and DuckDB embeddings

> **Status: deferred investigation.** OSII currently builds a derived FAISS
> index and mapping files for semantic retrieval. This note records a question
> to evaluate before changing that implementation. It is not a decision to
> replace FAISS or to add DuckDB as a required runtime dependency.

## Question

Could OSII store embedding results as independently inspectable Parquet
artifacts and use DuckDB to filter and search them, instead of depending on one
monolithic FAISS index?

The motivation is architectural as much as performance-related. Individual
embedding artifacts may make incremental work, inspection, export, scoped
queries, and partial rebuilds easier to understand. DuckDB could make the
metadata and vector-bearing rows queryable with ordinary SQL rather than a
special-purpose index alone.

## Current boundary

Embeddings are derived and rebuildable. The canonical evidence remains the
source file, extracted text, chunk manifest, provenance, and scope definition
inside `.osii`. A vector index must never become the only record of a text
segment or its source location.

Current documentation describes the derived embedding area as including a
FAISS index, mapping data, and metadata. Any investigation must preserve these
invariants:

- do not mix vectors produced by incompatible models, dimensions, or
  normalization rules;
- retain the exact embedding model and configuration with every result;
- preserve stable links to object, extraction version, segment, and source
  location;
- honor OSII root, folder, collection, and object scopes before ranking;
- keep BM25 and other local retrieval paths available when semantic retrieval
  is unavailable;
- allow all derived embedding data to be deleted and rebuilt without harming
  canonical evidence.

## Candidate representation to investigate

Treat an embedding file as a derived artifact associated with one bounded
input—preferably an object plus an extraction version, or another clearly
defined batch—not necessarily one tiny file per vector. A file per vector is
likely to create a small-file problem and should be measured rather than
assumed.

One possible layout is:

```text
.osii/
  embeddings/
    spaces/
      <embedding-space-fingerprint>/
        meta.toml
        objects/
          <file-id>--<extraction-id>.parquet
```

Each Parquet row would represent one embedded retrieval chunk and include at
least:

```text
file_id
extraction_id
segment_id
chunk_id
source_relpath
char_start
char_end
page
embedding_model
embedding_dimension
normalization
vector
created_at
```

The embedding-space directory name must be derived from the properties that
make vectors compatible, not merely a friendly model label. The investigation
should determine the smallest reliable fingerprint.

## Candidate search design

DuckDB would first select only the Parquet files and rows permitted by the
requested scope. It could then:

1. filter by embedding-space fingerprint and requested scope;
2. join chunk identifiers to current OSII metadata when needed;
3. compute or delegate vector similarity ranking;
4. return the same provenance-bearing retrieval result shape used today.

The investigation must compare at least three approaches:

- exact similarity ranking over DuckDB-selected vectors;
- a DuckDB-compatible vector/ANN capability, if it is mature and deployable;
- a hybrid design where Parquet is the portable authoritative derived vector
  representation and FAISS remains an optional acceleration built from it.

The hybrid design may be the safest outcome. It would preserve a transparent
and portable vector artifact while retaining FAISS where approximate-nearest-
neighbor performance is materially better.

## Questions a prototype must answer

- What is the practical file granularity: one object, one extraction run, one
  partition, or another bounded unit?
- Can DuckDB query the chosen vector representation efficiently on macOS,
  Windows, and Linux without a fragile native dependency story?
- Is exact ranking fast enough for expected local library sizes and scoped
  searches? If not, where does an ANN accelerator become necessary?
- Can the system prune files before reading vectors for folder, collection,
  and object searches?
- How are additions, re-extractions, source deletion, and model changes
  represented without rewriting unrelated embedding artifacts?
- How do compaction, checksums, schema evolution, and corrupt/missing Parquet
  files behave?
- Does the resulting implementation improve inspection and export enough to
  justify another storage format and query engine?

## Suggested evaluation

Build a narrow, non-default prototype using a fixed corpus and one embedding
space. Measure:

- build time and incremental-update time;
- on-disk size and file count;
- cold and warm search latency at root, folder, collection, and object scope;
- ranking agreement with the current FAISS path for the same vectors;
- behavior after an extraction version changes or a source is deleted;
- ability to inspect one file's embeddings and trace a result back to a source
  segment without application-specific tooling;
- packaging and cross-platform installation complexity.

The prototype should emit ordinary OSII retrieval results and run beside the
current FAISS implementation. It must not migrate or delete a user's existing
embedding index.

## Deliberate non-goals

- Do not store source documents or canonical extracted text in Parquet merely
  because embeddings are there.
- Do not make DuckDB the canonical OSII store or a requirement for lexical
  search, browsing, or local/model-free operation.
- Do not expose raw vectors as a substitute for provenance or source text.
- Do not replace FAISS solely because Parquet is more inspectable; validate the
  operational and retrieval tradeoffs first.

## Revisit trigger

Revisit when incremental embedding rebuilds, portable vector export, scoped
semantic search, or inspection of embedding artifacts becomes a concrete user
need, rather than a theoretical improvement.
