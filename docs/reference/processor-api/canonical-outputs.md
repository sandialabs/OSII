# Canonical Processor API outputs

OSII has four processor kinds. Their outputs are deliberately different:

| Processor kind | Canonical output |
|---|---|
| Extractor | Ordered, grounded `TextSegment` records plus optional source-derived artifacts |
| Synthesizer | Grounded Markdown plus citations |
| Embedder | Ordered numeric vectors with model and dimension identity |
| Enricher | One or more standard artifacts: `table`, `knowledge_graph`, `entity_list`, or `wiki_markdown` |

The four names in the last row are **enrichment artifact types**, not extractor
types. A wiki builder consumes already extracted text and may combine many
documents, so it is an enricher even when people informally call it a wiki
extractor.

## Extraction outputs

Every successful `ExtractionResponse` contains unique, ordered text segments.
Each segment has text, a `segment_type`, source grounding, and optional related
segment IDs. `segment_type` is descriptive and extensible rather than a closed
enum; common values include `text`, `page_text`, `table_row`, and
`image_description`. Consumers must rely on the grounded fields, not assume a
processor-specific segment type exists.

Optional extraction artifacts must be source-derived: page images, detected
figures, a directly parsed source table, or similar representations of the
input. A generated summary, entity interpretation, knowledge graph, or wiki is
not canonical extraction and belongs in synthesis or enrichment.

## Enrichment outputs

Processor API v1 accepts exactly four discriminated standard artifact shapes:

- `table`
- `knowledge_graph`
- `entity_list`
- `wiki_markdown`

The dashboard and MCP tools dispatch on `artifact_type`, so an SME can implement
a conforming backend without adding processor-specific frontend code. See
[standard enrichment artifact formats](standard-artifacts.md) for every field.
