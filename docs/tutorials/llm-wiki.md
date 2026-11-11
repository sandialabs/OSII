# Generate an LLM wiki

LLM wikis are optional, derived knowledge products. They are not built into
OSII Core. Two independent Processor API enrichers live in
`osii-processor-modules/llm-wiki-enrichers`:

- **Readable LLM wiki** produces a traditional, cited narrative page.
- **Concept and entity LLM wiki** produces a concept/entity-oriented wiki plus
  a standard entity list and sortable concept table. It adapts the work on the
  divergent `dev-aditya` branch to the current Processor API.

Both use the current primary extraction and can run over a document, folder,
collection, or the entire root. Core sends bounded text to the selected
enricher and remains the only component that writes `.osii`.

## Before you start

1. Start OSII with `make dev` on macOS/Linux or
   `.\scripts\osii.ps1 dev` on Windows.
2. Open **Setup**, connect Ollama or an OpenAI-compatible provider, and select
   a chat-capable model connection.
3. Start the optional wiki processors from **Setup → Advanced & diagnostics →
   Local capability services**. Or use a separate terminal:

   Use the source commands in
   `osii-processor-modules/llm-wiki-enrichers/README.md`. Container build commands
   are archived; local capability controls start the Python services.
4. In **Setup → Register running processor**, register
   `http://127.0.0.1:8099` and `http://127.0.0.1:8100`.

For source-only development commands and OpenAI-compatible routing, see
`osii-processor-modules/llm-wiki-enrichers/README.md` in the repository.

## Generate and compare

Open a processed document's **Wiki** tab, a collection's **Wikis & products**
section, or **Library wikis & products → Wiki** on Files. Choose either method and select
**Generate wiki**. Saved Wiki Markdown outputs are discovered by
their standard `artifact_type`, not by a hard-coded processor name or filename,
so another SME's conforming wiki enricher appears in the same view.

The concept/entity processor also returns structured artifacts. Open the
regular **Other products** view to browse and sort those outputs through the
generic entity-list and table renderers.

Processor settings, including the prompt, temperature, and input budget, are
descriptor-driven and appear in Setup. The chosen model connection is a tool
binding in `tools.toml`, not a processor-specific URL. No frontend change is
required to expose the same supported schema fields from a new processor.

## Models, progress, and editing

The writing-model field shows the actual configured model. Library defaults are
selected automatically; a missing old `top`/`mid` placeholder inherits that
default. A valid custom binding is preserved. Incompatible choices are rejected
before a job starts. Generation uses the persistent worker and appears in
**Activity**. Navigate away and return without losing its status; failed work
can be retried on the same saved text inputs.

Every document, folder, collection, and library wiki has **Read**, **Edit**, and
**History**. A draft survives navigation on this browser. Save creates a revision;
stale saves preserve the draft and require comparison with the latest revision.
Regeneration leaves human edits visible and saves a candidate for review. Use
**History → Use this revision** to explicitly choose a candidate or older version.
Edited passages retain citation provenance but require grounding review.

## Storage and provenance

Core saves each returned artifact under the requested scope's `enrichments/`
directory. Filenames include the processor descriptor and artifact ID, so both
wiki varieties can coexist and be regenerated independently. Sidecar metadata
records the processor URL, processor version, artifact ID, expert context,
connection alias, actual provider model, prompt version, and citations.

The deprecated `osii.enrichment.llm_wiki.LlmWikiEnricher` import is only a
temporary forwarding shim for older Python demos. It is not registered as a
Core capability and contains no wiki-generation implementation.

Every wiki payload uses the canonical `wiki_markdown` format. The
concept/entity processor additionally uses `entity_list` and `table`. Review
[canonical Processor API outputs](../reference/processor-api/canonical-outputs.md)
for the distinction between extraction outputs and enrichment artifact types.

## Reuse and improve knowledge from a coding harness

The `osii-mcp` documentation assistant also supports a harness-driven wiki loop.
Search with `search_documentation`, inspect original passages with
`get_documentation_evidence`, then capture reusable coding guidance or
experimental lessons with `save_wiki_page`. The connected harness supplies the
LLM synthesis; Core validates citation spans and persists standard
`wiki_markdown` artifacts. No additional model connection is required.

Pages record software/version applicability, source fingerprints and revisions.
Current matching pages can avoid repeated source searches; stale or untracked
pages trigger source retrieval. Matching is heuristic and all generated pages
are unreviewed, so verify applicability and distinguish reported observations
from inferred advice. Use `get_wiki_page` to read a page before revising it;
updates require its current revision to avoid overwriting another contribution.
The MCP package's `README.md` documents STDIO/HTTP setup and request formats.
