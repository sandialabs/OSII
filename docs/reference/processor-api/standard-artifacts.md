# Standard enrichment artifact formats

The discriminator is always `artifact_type`. Version 1 defines four formats.
SDK validation rejects undocumented fields so formats evolve deliberately.

## Table

Fields: `title`, optional `description`, `columns`, `rows`, and optional
`row_provenance`. Column keys address values in every row. Supported data types
are `string`, `number`, `integer`, `boolean`, `date`, `datetime`, and `json`.

The dashboard renders a scrollable table. Agents can inspect columns, filter
rows in future tool surfaces, and follow row provenance.

## Knowledge graph

Fields: `title`, optional `description`, `nodes`, and `edges`.

Nodes contain `id`, `label`, `entity_type`, optional `properties`, and
provenance. Edges contain `id`, `source`, `target`, `relation`, optional
properties, and provenance. Edge endpoints must name node IDs.

The dashboard renders graph statistics, node cards, and relationship tables;
an interactive canvas can be added without changing the artifact.

## Entity list

Fields: `title`, optional `description`, and `entities`. Each entity has `id`,
`name`, `entity_type`, aliases, attributes, and source mentions.

The dashboard groups and displays entities with their attributes. Agents can
use IDs and mentions for grounded follow-up.

## Wiki Markdown

Fields: `title`, `markdown`, and optional citations. Markdown may use GFM,
mathematics, tables, and headings. Raw HTML is not part of the contract.

The dashboard renders sanitized Markdown using its existing Markdown stack.

## Provenance

A provenance reference may contain `file_id`, `segment_id`, page, character
offsets, and source-origin details. Producers should populate the narrowest
grounding they can defend. Consumers must not infer missing grounding.

Agents discover these through the MCP tools `list_enrichment_artifacts` and
`get_enrichment_artifact`. The latter returns the same JSON consumed by the
dashboard, so processor authors do not need separate UI and agent integrations.
