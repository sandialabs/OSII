# Standard artifact specifications

Version 1 defines four inspectable knowledge formats: `table`,
`knowledge_graph`, `entity_list`, and `wiki_markdown`. The discriminator is
`artifact_type`, not a processor name or filename. The dashboard and MCP
consume the same formats, so an enricher does not need a custom UI contract.

Every object below sits inside an `Artifact.standard_data` envelope.
Enrichment requires that payload; extraction may use it for a source-derived
table or other faithful source representation. Generated interpretation stays
in enrichment. See the [enricher spec](enrichment.md) for the full response and
the [artifact envelope](index.md#artifact-envelope) for payload rules.

The examples are complete valid `standard_data` values, not entire responses.
Optional fields are omitted where they are unnecessary. All typed objects
reject unknown fields; free dictionaries remain extensible.

## Table

Use a table for typed columns and grounded rows. SDK model:
`TableArtifactData`. Dashboard: sortable/scrollable table with visible-column
selection and Copy CSV. The stored artifact remains JSON.

### Fields

| Field | Type | Required / default | Meaning |
| --- | --- | --- | --- |
| `artifact_type` | string | No; `"table"` | Required discriminator when parsing the union over HTTP |
| `title` | string | Yes | Human-readable title |
| `description` | string or null | No; `null` | What the table represents |
| `columns` | TableColumn[] | Yes; may be empty | Ordered column definitions |
| `rows` | object[] | Yes; may be empty | Row values addressed by column keys |
| `row_provenance` | ProvenanceRef[][] | No; `[]` | Evidence list per row; if populated, length equals row count |

A `TableColumn` has:

| Field | Type | Required / default | Meaning |
| --- | --- | --- | --- |
| `key` | string | Yes | Unique column key |
| `label` | string | Yes | Display label |
| `data_type` | string | No; `"string"` | `string`, `number`, `integer`, `boolean`, `date`, `datetime`, or `json` |
| `unit` | string or null | No; `null` | Stated measurement unit |
| `description` | string or null | No; `null` | Column interpretation |

### Example

```json
{
  "artifact_type": "table",
  "title": "Document word counts",
  "columns": [
    {"key": "document", "label": "Document", "data_type": "string"},
    {"key": "words", "label": "Words", "data_type": "integer"}
  ],
  "rows": [{"document": "sensor.txt", "words": 3}],
  "row_provenance": [[{"file_id": "file-1", "char_start": 0, "char_end": 18}]]
}
```

**Validation:** column keys must be unique. Populated `row_provenance` must
match row count; an individual row's evidence list can be empty. Row keys and
values are not validated against columns/data types. Producers must check
them and state missing-value, unit, and date/time conventions. v1 does not
specify a date serialization format or unit vocabulary.

## Knowledge graph

Use a graph for entities and grounded relationships. SDK model:
`KnowledgeGraphArtifactData`. Dashboard: statistics, node cards, and
relationship tables; this contract does not promise an interactive graph canvas.

### Fields

| Field | Type | Required / default | Meaning |
| --- | --- | --- | --- |
| `artifact_type` | string | No; `"knowledge_graph"` | Union discriminator |
| `title` | string | Yes | Graph title |
| `description` | string or null | No; `null` | Interpretation |
| `nodes` | KnowledgeGraphNode[] | Yes; may be empty | Identified nodes |
| `edges` | KnowledgeGraphEdge[] | Yes; may be empty | Directed source/target relationships |

Each node has:

| Field | Type | Required / default | Meaning |
| --- | --- | --- | --- |
| `id` | string | Yes | Unique within this graph's nodes |
| `label` | string | Yes | Human-readable label |
| `entity_type` | string | Yes | Method-defined type; no enum |
| `properties` | object | No; `{}` | Method-specific attributes |
| `provenance` | ProvenanceRef[] | No; `[]` | Evidence for this node |

Each edge has:

| Field | Type | Required / default | Meaning |
| --- | --- | --- | --- |
| `id` | string | Yes | Unique within this graph's edges |
| `source`, `target` | string | Yes | Existing node IDs |
| `relation` | string | Yes | Method-defined relationship; no enum |
| `properties` | object | No; `{}` | Method-specific relationship details |
| `provenance` | ProvenanceRef[] | No; `[]` | Evidence for this edge |

### Example

```json
{
  "artifact_type": "knowledge_graph",
  "title": "Sensor checks",
  "nodes": [
    {"id": "sensor-1", "label": "Sensor", "entity_type": "equipment"},
    {"id": "check-1", "label": "Check", "entity_type": "event"}
  ],
  "edges": [{
    "id": "observed-in",
    "source": "sensor-1",
    "target": "check-1",
    "relation": "tested_in",
    "provenance": [{"file_id": "file-1", "char_start": 0, "char_end": 18}]
  }]
}
```

**Validation:** node IDs and edge IDs are unique within their respective
lists; edge endpoints must exist. The schema does not prove a relationship,
validate property semantics, or prescribe cross-artifact identity. Nodes and
edges may have no provenance; document when that is acceptable.

## Entity list

Use an entity list for identified people, equipment, concepts, or other
domain entities with source mentions. SDK model: `EntityListArtifactData`.
Dashboard: grouped entities and attributes.

### Fields

| Field | Type | Required / default | Meaning |
| --- | --- | --- | --- |
| `artifact_type` | string | No; `"entity_list"` | Union discriminator |
| `title` | string | Yes | List title |
| `description` | string or null | No; `null` | Interpretation |
| `entities` | Entity[] | Yes; may be empty | Identified entities |

Each entity has:

| Field | Type | Required / default | Meaning |
| --- | --- | --- | --- |
| `id` | string | Yes | Unique within this list |
| `name` | string | Yes | Primary name |
| `entity_type` | string | Yes | Method-defined type; no enum |
| `aliases` | string[] | No; `[]` | Alternate names |
| `attributes` | object | No; `{}` | Method-specific properties |
| `mentions` | ProvenanceRef[] | No; `[]` | Locations where evidence occurs |

### Example

```json
{
  "artifact_type": "entity_list",
  "title": "Equipment mentions",
  "entities": [{
    "id": "sensor-1",
    "name": "sensor",
    "entity_type": "equipment",
    "aliases": [],
    "attributes": {},
    "mentions": [{"file_id": "file-1", "char_start": 4, "char_end": 10}]
  }]
}
```

**Validation:** entity IDs must be unique. Alias uniqueness, entity resolution,
mention/source membership, and span accuracy are not enforced. Entity IDs do
not automatically become global corpus identities.

## Wiki Markdown

Use a wiki for reusable readable knowledge with citations. SDK model:
`WikiMarkdownArtifactData`. Dashboard: sanitized Markdown with GFM,
mathematics, tables, and headings. Raw HTML is not a promised render format.

### Fields

| Field | Type | Required / default | Meaning |
| --- | --- | --- | --- |
| `artifact_type` | string | No; `"wiki_markdown"` | Union discriminator |
| `title` | string | Yes | Wiki title |
| `markdown` | string | Yes; may be empty | Derived readable content |
| `citations` | ProvenanceRef[] | No; `[]` | Supporting source locations |

### Example

```json
{
  "artifact_type": "wiki_markdown",
  "title": "Sensor check",
  "markdown": "The supplied report states that the sensor passed.",
  "citations": [{"file_id": "file-1", "char_start": 0, "char_end": 18}]
}
```

**Validation:** field shape only. Citation support and Markdown claim-to-source
association are not enforced. Multiple wiki artifacts/processors can coexist
within a scope; label uncertainty and model-generated interpretation.

## Provenance, confidence, and empty results

All evidence lists reuse [ProvenanceRef](synthesis.md#provenanceref).
References may contain source ID, segment ID, one-based page, zero-based
half-open character span, and `source_origin`. Populate the narrowest
grounding you can defend. Consumers must not invent missing grounding.

None of these formats has a typed `confidence` property. A method can carry
a documented score in graph properties, entity attributes, or artifact
metadata, but this is not a common quality contract. State score meaning,
granularity, scale, method, and unknown-value handling; do not present a
heuristic or model self-rating as a probability of correctness.

All four formats can represent empty content. Enrichment still requires at
least one artifact and should explain an empty outcome through response
warnings. A returned artifact with no evidence is not automatically useful or
trustworthy just because its JSON validates.

Agents discover saved enrichment through MCP `list_enrichment_artifacts`
and `get_enrichment_artifact`; the latter returns the stored JSON used by
the dashboard. Direct processor calls create no saved artifact.

## Compliance checklist

- [ ] Include the correct `artifact_type` inside `standard_data` for wire parsing.
- [ ] Supply all required fields and no unknown typed fields.
- [ ] Check IDs, graph endpoints, column keys, and row-provenance alignment.
- [ ] Validate row types, source membership, spans, and semantic accuracy yourself.
- [ ] Distinguish source-derived extraction from derived enrichment.
- [ ] Document method-specific dictionaries, uncertainty, and empty results.
- [ ] Test both the SDK response and Core's stored representation.
