# Generate an LLM wiki

An LLM wiki is a derived OSII knowledge product: grounded Markdown generated
from the current primary extraction of one document or a collection. It is an
enrichment rather than canonical text, so it can be regenerated without
changing the source document or its extraction.

## Before you start

1. Start OSII with `make dev` on macOS/Linux or
   `.\scripts\osii.ps1 dev` on Windows.
2. Open **Tools → Model providers**.
3. Confirm that Ollama is connected and select an installed synthesis model.
   The small US-origin starter model is `llama3.2:1b` from Meta.
4. Intake at least one supported document.

OSII does not silently use the extractive preview for this feature. If no
model-backed synthesizer is ready, wiki generation stops with an actionable
message rather than calling the output an LLM wiki.

## One-document demonstration

1. Open **Files** and select a processed document.
2. Open its **Wiki** tab.
3. Select **Generate Wiki**.
4. Keep working elsewhere if desired. Generation runs as a background job and
   the page refreshes when the artifact is ready.

The wiki uses the document's current primary extraction. If a different
extraction is later made primary, OSII marks the wiki stale so it can be
regenerated from the new text.

## Collection demonstration

1. Create or open a collection containing processed documents.
2. Select **Generate Wiki** in the LLM Wiki panel.
3. The result appears directly in the collection view above its document grid.

The collection wiki is generated only from extracted documents that belong to
that collection. Factual statements are prompted to cite source file IDs in
square brackets. OSII always adds an inspectable Sources section when the model
does not produce one, and the standard artifact also stores structured
file-level provenance references.

## Storage and portability

The stable artifact paths are:

```text
objects/<file-id>/enrichments/wiki--llm_wiki.json
collections/<collection-id>/enrichments/wiki--llm_wiki.json
```

Each payload uses the Processor API `wiki_markdown` standard format. Metadata
records the actual synthesizer, provider, model, input counts, citations, and
whether source text was truncated to fit the configured input budget. The
default budget is 60,000 characters across the scope and may be changed with
the enricher configuration field `max_input_chars`. For collections of two to
eight documents, the demonstration enricher first creates a short grounded
brief for each source before composing the collection wiki. This helps small
local models represent every member; `max_brief_documents` controls that
threshold for machines with a larger model or more generation capacity.

The dashboard, REST enrichment APIs, and MCP enrichment tools all consume the
same saved artifact. Ollama and its model files remain outside OSII; another
model-backed Processor API synthesizer can create the same knowledge product.
