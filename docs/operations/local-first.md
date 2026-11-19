# Working without a model

After dependencies are installed, OSII can extract text, browse documents, run
keyword search, and create simple derived products without a model connection.
Initial dependency installation and optional processor setup may need network
access. OCR requires native Tesseract and its language data.

| Capability | Model-free behavior | Optional model-backed behavior |
| --- | --- | --- |
| Extraction | Text-layer PDF, Office, and plain-text readers; Tesseract OCR | A separately selected document processor |
| Synthesis | Cited source-excerpt preview | Generated narrative from a selected chat model |
| Search | BM25 keyword retrieval | Semantic or hybrid retrieval with a matching vector index |
| Enrichment | Statistics and keyword artifacts | Wikis and domain analysis |
| Chat | Extractive answer | Model-generated grounded answer |

Lexical hashing is an optional compatibility embedder. It tests vector plumbing
and shared-wording similarity; it is not a semantic language model.

## Choose processing explicitly

Use **Setup** to select readers and any model connections. In **Intake**, choose
text-only processing when you want no model calls. Selecting summaries or
embeddings requires the corresponding configured method. Starting a service or
saving a connection does not process your documents.

Keep extracted text and search indexes separate. A new embedding model requires
a compatible index. Installing a model does not re-embed an existing library.
Use [model endpoints](model-endpoints.md) for connection setup and
[extraction versions](../reference/extraction-versions.md) for OCR upgrades.

## When a service is unavailable

- Chat and synthesis follow their configured provider order and report which
  provider produced the result. An extractive result is identified as such.
- Semantic search reports keyword fallback when query embeddings are unavailable.
- Embedding retries preserve their checkpoint and model identity; they do not
  silently switch models in the same index.
- OCR needs a working extractor. A running HTTP service alone does not prove
  that its native executable and language data are available.

Pause, resume, cancel, and retry are available in Activity. Controls take effect
between safe stages; an in-flight provider request may finish first.

See the [startup guide](runbook-development.md) for installation and troubleshooting,
and the [wiki tutorial](../tutorials/llm-wiki.md) for optional generated products.
