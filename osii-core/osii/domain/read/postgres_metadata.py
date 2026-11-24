"""Read saved document labels from PostgreSQL without loading product bodies."""

from __future__ import annotations

from typing import TYPE_CHECKING

from osii.domain.document_metadata import METADATA_ENRICHER, synthesis_labels

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection


def postgres_document_labels(connection: Connection, file_ids: list[str]) -> dict[str, dict]:
    from sqlalchemy import text

    titles = connection.execute(text("""
        SELECT d.file_id, m.metadata AS manual, m.metadata_sources, COALESCE(t.metadata,e.metadata) AS suggested,
               s.labels AS synthesis, s.processor AS synthesis_processor,
               CASE WHEN t.metadata IS NOT NULL THEN :metadata_enricher ELSE e.processor END AS suggestion_processor,
               CASE WHEN NOT COALESCE((d.metadata->'stale'->>'syntheses')::boolean, false)
                    THEN jsonb_build_object('document_metadata',d.metadata->'document_metadata',
                        'document_title',d.metadata->'document_title','title_method',d.metadata->'title_method') END AS legacy
        FROM documents d
        LEFT JOIN LATERAL (
            SELECT r.data->'document_metadata' AS metadata, r.data->'metadata_sources' AS metadata_sources
            FROM scope_products p JOIN scope_revisions r ON r.id=p.current_revision
            WHERE p.scope_type='object' AND p.scope_id=d.file_id
              AND p.filename='document_metadata--manual.json'
        ) m ON true
        LEFT JOIN LATERAL (
            SELECT jsonb_object_agg(entry->>'field', entry - 'field') AS metadata
            FROM (
                SELECT r.data->'rows' AS rows FROM scope_products p
                JOIN scope_revisions r ON r.id=p.current_revision
                WHERE p.scope_type='object' AND p.scope_id=d.file_id AND p.method=:metadata_enricher
                  AND jsonb_typeof(r.data->'rows')='array'
                  AND r.provenance->'processing_input'->'inputs'->0->>'text_sha256'=encode(sha256(convert_to(
                      COALESCE(d.metadata->'edited_representation'->>'text',d.text),'UTF8')),'hex')
                ORDER BY r.created_at DESC,r.id DESC LIMIT 1
            ) current_table CROSS JOIN LATERAL jsonb_array_elements(current_table.rows) entry
            WHERE entry->>'field' IS NOT NULL
        ) t ON m.metadata IS NULL
        LEFT JOIN LATERAL (
            SELECT item->'metadata'->'document_metadata' AS metadata,
                   a.payload->'response'->'processor'->>'name' AS processor
            FROM artifacts a CROSS JOIN LATERAL jsonb_array_elements(
                CASE WHEN jsonb_typeof(a.payload->'response'->'artifacts')='array'
                     THEN a.payload->'response'->'artifacts' ELSE '[]'::jsonb END) item
            WHERE a.file_id=d.file_id AND a.kind='enrichment' AND item->>'kind'='document_metadata'
              AND a.payload->>'input_text_sha256'=encode(sha256(convert_to(
                  COALESCE(d.metadata->'edited_representation'->>'text',d.text),'UTF8')),'hex')
            ORDER BY a.payload->>'created_at' DESC NULLS LAST,a.id DESC LIMIT 1
        ) e ON m.metadata IS NULL AND t.metadata IS NULL
        LEFT JOIN LATERAL (
            SELECT labels, processor FROM (
                SELECT a.payload->'response'->'metadata' AS labels,
                       a.payload->'response'->'processor'->>'name' AS processor,
                       a.payload->>'input_text_sha256' AS input_hash,
                       a.payload->>'created_at' AS created_at, a.id::text AS id
                FROM artifacts a WHERE a.file_id=d.file_id AND a.kind='synthesis'
                UNION ALL
                SELECT r.provenance->'batch_processor_metadata'->0 AS labels,
                       r.provenance->'processor'->>'name' AS processor,
                       r.provenance->'processing_input'->'inputs'->0->>'text_sha256' AS input_hash,
                       r.created_at::text AS created_at, r.id::text AS id
                FROM scope_products p JOIN scope_revisions r ON r.id=p.current_revision
                WHERE p.scope_type='object' AND p.scope_id=d.file_id AND p.family='synthesis'
                  AND r.provenance->'batch_processor_metadata'->1 IS NULL
                  AND (r.provenance->'batch_processor_metadata'->0) ? 'document_metadata'
            ) candidates
            WHERE input_hash=encode(sha256(convert_to(
                  COALESCE(d.metadata->'edited_representation'->>'text',d.text),'UTF8')),'hex')
            ORDER BY created_at DESC NULLS LAST,id DESC LIMIT 1
        ) s ON m.metadata IS NULL AND t.metadata IS NULL AND e.metadata IS NULL
        WHERE d.active AND d.file_id=ANY(:ids)
    """), {'ids': file_ids, 'metadata_enricher': METADATA_ENRICHER}).mappings()
    result = {}
    for row in titles:
        metadata = row["manual"] or row["suggested"]
        labels = {"document_metadata": metadata} if metadata else row["synthesis"] or row["legacy"] or {}
        normalized = synthesis_labels(labels)
        if row["manual"] and row["metadata_sources"]:
            normalized["metadata_sources"] = row["metadata_sources"]
        elif normalized.get("document_metadata") and not row["manual"]:
            normalized["metadata_processor"] = row["suggestion_processor"] if row["suggested"] else row["synthesis_processor"]
        result[row["file_id"]] = normalized
    return result
