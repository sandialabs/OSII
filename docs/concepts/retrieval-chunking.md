# Retrieval chunking and overlap

OSII uses one derived chunk manifest for both BM25 and vector retrieval. This
keeps lexical and semantic results comparable and preserves the exact character
offsets needed to open a match in its source document.

## Recommended default

The default strategy is `sentence_window` with:

- a maximum of 768 characters per chunk;
- a target overlap of 128 characters;
- paragraph boundaries preferred when they fit the window;
- sentence boundaries used otherwise; and
- a word boundary only as a fallback for unusually long sentences.

This is a moderate starting point, not a claim that one size fits every corpus.
Recent evaluations find that smaller chunks favor concise fact lookup while
larger chunks favor questions needing broader context. Research on structured
financial documents also supports respecting document elements instead of
blindly cutting text. Finally, RAGChecker found that overlap alone produces
only modest gains, so OSII uses enough overlap to protect boundary context
without filling retrieval results with near-duplicates.

References:

- [Rethinking Chunk Size for Long-Document Retrieval](https://arxiv.org/abs/2505.21700)
- [Financial Report Chunking for Effective Retrieval Augmented Generation](https://arxiv.org/abs/2402.05131)
- [RAGChecker](https://arxiv.org/abs/2408.08067)

## Provenance and retrieval behavior

Every derived chunk records:

- exact `char_start` and `char_end` offsets;
- its primary extraction version;
- source manifest segment IDs and PDF pages when available;
- previous and next chunk IDs; and
- the actual overlap with the preceding chunk.

Search suppresses results that overlap an already selected result by at least
65 percent of the shorter span. Ordinary 128-character boundary overlap is
retained; near-duplicate high-overlap results do not consume the answer's
evidence budget. Search and chat citations carry the source page and manifest
segment back to the document Split View.

Changing the method, size, overlap, extraction version, model, or source text
invalidates an interrupted embedding checkpoint and requires rebuilding the
derived indexes. Canonical extracted text is unchanged.

## Choosing another strategy

Expand **Retrieval chunking** beside **Build semantic embeddings** in Intake or
Process library.

- **Sentence-aligned windows** are the normal choice for prose and mixed
  technical documents.
- **Paragraphs** retain the previous no-overlap behavior and are useful when
  the source already has consistently sized structural units.
- **Fixed character windows** provide deterministic compatibility testing.

The overlap must be smaller than the chunk size. Evaluate settings against the
questions and citation quality that matter for the actual corpus rather than
tuning only by intuition.
