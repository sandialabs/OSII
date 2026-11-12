# Canonical Processor API outputs

OSII has four processor kinds. Their outputs are deliberately different:

| Processor kind | Canonical output |
|---|---|
| Extractor | Ordered, grounded `TextSegment` records plus optional source-derived artifacts |
| Synthesizer | Grounded Mathpix Markdown plus citations and optional structured document metadata |
| Embedder | Ordered numeric vectors with model and dimension identity |
| Enricher | One or more standard artifacts: `table`, `knowledge_graph`, `entity_list`, or `wiki_markdown` |

The four names in the last row are **enrichment artifact types**, not extractor
types. A wiki builder consumes already extracted text and may combine many
documents, so it is an enricher even when people informally call it a wiki
extractor.

## Extraction outputs

The extraction contract calls for unique, ordered text segments.
Each segment has text, a `segment_type`, source grounding, and optional related
segment IDs. `segment_type` is descriptive and extensible rather than a closed
enum; common values include `text`, `page_text`, `table_row`, and
`image_description`. Consumers must rely on the grounded fields, not assume a
processor-specific segment type exists.

The schema permits an empty segment list, but Core's current remote extractor
marks that result as a failed extraction. See the
[extractor spec](extraction.md) for complete JSON, field defaults, OCR
confidence/geometry, and partial-result behavior.

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

## A valid shape is not proof of a correct result

The SDK validates structure and selected invariants. It does not prove reading
order, confidence calibration, citation support, or numerical model
compatibility. Core integration also differs by kind: its remote enricher
still accepts legacy payloads rather than enforcing the entire typed v1
response. See the [backend review](index.md#backend-review-what-is-enforced-today)
before treating a documented requirement as an automatic guarantee.
