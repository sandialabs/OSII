# Generate an LLM wiki

LLM wikis are optional, derived knowledge products. They are not built into
OSII Core. Two independent Processor API enrichers live in
`osii-toolbox/llm-wiki-enrichers`:

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

   ```bash
   make toolbox-build TOOL=llm-wikis
   make toolbox-run TOOL=llm-wikis
   ```

   PowerShell uses `toolbox-build -Tool llm-wikis` and
   `toolbox-run -Tool llm-wikis` through `scripts\osii.ps1`.
4. In **Setup → Register running processor**, register
   `http://127.0.0.1:8099` and `http://127.0.0.1:8100`.

For source-only development commands and OpenAI-compatible routing, see
`osii-toolbox/llm-wiki-enrichers/README.md` in the repository.

## Generate and compare

Open a processed document's **Wiki** tab, a collection's **Enrichments**
drawer, or root **Library Insights → Wiki**. Choose either method and select
**Generate selected wiki**. Saved Wiki Markdown outputs are discovered by
their standard `artifact_type`, not by a hard-coded processor name or filename,
so another SME's conforming wiki enricher appears in the same view.

The concept/entity processor also returns structured artifacts. Open the
regular **Enrichments** view to browse and sort those outputs through the
generic entity-list and table renderers.

Processor settings, including the prompt, temperature, and input budget, are
descriptor-driven and appear in Setup. The chosen model connection is a tool
binding in `tools.yml`, not a processor-specific URL. No frontend change is
required to expose the same supported schema fields from a new processor.

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
