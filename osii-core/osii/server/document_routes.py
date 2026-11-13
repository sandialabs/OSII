"""Body-free document navigation and on-demand saved product reads."""
from typing import Any

from fastapi import Depends, HTTPException
from sqlalchemy import text

from osii.persistence.postgres import PostgresStore
from osii.server.auth import require

INLINE_PRODUCT_BYTES = 4 * 1024 * 1024


def register_document_routes(app: Any, store: PostgresStore) -> None:
    def active(file_id: str) -> None:
        with store.engine.connect() as connection:
            row = connection.execute(text(
                'SELECT file_id FROM documents WHERE file_id=:id AND active'
            ), {'id': file_id}).first()
        if row is None:
            raise HTTPException(404, 'Document not found')

    @app.get('/api/objects/{file_id}/extractions/catalog')
    def extractions(file_id: str, actor=Depends(require())):
        active(file_id)
        with store.engine.connect() as connection:
            rows = connection.execute(text("""
                SELECT e.id,e.created_at,e.response->'processor' AS processor,
                    COALESCE(jsonb_array_length(e.response->'segments'),0) AS segment_count,
                    e.id=d.metadata->>'primary_extraction_id' AS is_primary
                FROM extractions e JOIN documents d ON d.file_id=e.file_id
                WHERE e.file_id=:id
                ORDER BY (e.id=d.metadata->>'primary_extraction_id') DESC NULLS LAST,
                    e.created_at DESC,e.id
            """), {'id': file_id}).mappings().all()
        result = [{**dict(row), 'primary': bool(row['is_primary'])} for row in rows]
        if result and not any(row['primary'] for row in result):
            result[0]['primary'] = True
        return {'items': result}

    @app.get('/api/objects/{file_id}/products/catalog')
    def products(file_id: str, actor=Depends(require())):
        active(file_id)
        with store.engine.connect() as connection:
            rows = connection.execute(text("""
                SELECT id,kind,
                    left(COALESCE(payload->'response'->'processor'->>'display_name',kind),240) AS title,
                    payload->>'created_at' AS created_at,
                    jsonb_path_query_array(payload,
                        '$.response.artifacts[0 to 15].standard_data.artifact_type') AS types
                FROM artifacts WHERE file_id=:id ORDER BY id
            """), {'id': file_id}).mappings().all()
            saved = connection.execute(text("""
                SELECT 'product:'||id AS id,family AS kind,left(title,240) AS title,
                    artifact_type AS type
                FROM scope_products WHERE scope_type='object' AND scope_id=:id
                ORDER BY filename
            """), {'id': file_id}).mappings().all()
            extraction_products = connection.execute(text("""
                SELECT 'extraction:'||id AS id,'extraction' AS kind,
                    left(COALESCE(response->'processor'->>'display_name','Extraction data'),240) AS title,
                    jsonb_path_query_array(response,
                        '$.artifacts[0 to 15].standard_data.artifact_type') AS types
                FROM extractions WHERE file_id=:id
                    AND COALESCE(jsonb_array_length(response->'artifacts'),0)>0
                ORDER BY created_at DESC,id
            """), {'id': file_id}).mappings().all()
        return {'items': [dict(row) for row in rows] + [dict(row) for row in extraction_products] + [
            {**dict(row), 'types': [row['type']]} for row in saved
        ]}

    @app.get('/api/objects/{file_id}/products/{product_id}')
    def product(file_id: str, product_id: str, actor=Depends(require())):
        active(file_id)
        if product_id.startswith('product:'):
            source = """
                SELECT jsonb_build_object('data',r.data,'created_at',r.created_at,
                    'title',p.title) AS payload
                FROM scope_products p JOIN scope_revisions r ON r.id=p.current_revision
                WHERE p.scope_type='object' AND p.scope_id=:file_id AND p.id=:id
            """
            identity = product_id[8:]
        elif product_id.startswith('extraction:'):
            source = """
                SELECT jsonb_build_object('response',jsonb_build_object(
                    'artifacts',response->'artifacts')) AS payload
                FROM extractions WHERE file_id=:file_id AND id=:id
            """
            identity = product_id[11:]
        else:
            source = 'SELECT payload FROM artifacts WHERE file_id=:file_id AND id=:id'
            identity = product_id
        # Filter in PostgreSQL before transferring an inline preview to the API.
        with store.engine.connect() as connection:
            row = connection.execute(text(
                'SELECT payload FROM (' + source + ') chosen '
                'WHERE octet_length(payload::text)<=:max_bytes'
            ), {'file_id': file_id, 'id': identity, 'max_bytes': INLINE_PRODUCT_BYTES}).mappings().first()
        if row is None:
            raise HTTPException(404,
                'Saved product unavailable or too large for an inline preview; '
                'inspect it through the Toolbox')
        payload = row['payload']
        stale = None
        if payload.get('input_extraction_id'):
            import hashlib
            from osii.domain.read.postgres import PostgresLibraryReader

            preferred = PostgresLibraryReader(store.engine).get_representation(file_id)
            stale = (
                not preferred
                or payload['input_extraction_id'] != preferred.representation_id
                or (payload.get('input_text_sha256') is not None
                    and payload['input_text_sha256'] != hashlib.sha256(preferred.text.encode()).hexdigest())
            )
        return {'id': product_id, 'payload': payload, 'stale': stale}
