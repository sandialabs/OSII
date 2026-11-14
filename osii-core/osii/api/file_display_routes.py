"""Shared file-display routes with explicit local/hosted persistence adapters."""
import json
from typing import Annotated
from pathlib import Path
from fastapi import Depends, FastAPI, Request
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import text
from sqlalchemy.engine import Engine
from osii.domain.file_display import FileDisplay, display_settings


class PreviewRequest(BaseModel):
    file_ids: list[Annotated[str, StringConstraints(min_length=1,max_length=200)]] = Field(max_length=48)


def postgres_previews(engine: Engine, file_ids: list[str]) -> dict[str, dict]:
    # Only bounded excerpts leave PostgreSQL; never fetch entire OCR/LLM bodies.
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT d.file_id,
                left(COALESCE(d.metadata->'edited_representation'->>'text',d.text),1200) AS text_preview,
                left(COALESCE(p.body,s.body,''),1000) AS synthesis_preview
            FROM documents d
            LEFT JOIN LATERAL (
                SELECT COALESCE(r.data->>'text',r.data->>'markdown') AS body
                FROM scope_products p JOIN scope_revisions r ON r.id=p.current_revision
                WHERE p.scope_type='object' AND p.scope_id=d.file_id AND p.family='synthesis'
                ORDER BY r.created_at DESC,r.id DESC LIMIT 1
            ) p ON true
            LEFT JOIN LATERAL (
                SELECT a.payload->'response'->>'markdown' AS body FROM artifacts a
                WHERE a.file_id=d.file_id AND a.kind='synthesis'
                ORDER BY a.payload->>'created_at' DESC NULLS LAST,a.id DESC LIMIT 1
            ) s ON true
            WHERE d.active AND d.file_id=ANY(:ids)
        """), {'ids':file_ids}).mappings().all()
    return {row['file_id']:dict(row) for row in rows}


def _read_prefix(path: Path, limit: int) -> str:
    try:
        with path.open(encoding='utf-8', errors='replace') as stream:
            return stream.read(limit)
    except FileNotFoundError:
        return ''


def sidecar_previews(root: Path, file_ids: list[str]) -> dict[str, dict]:
    from osii.domain.read.sidecar import SidecarLibraryReader
    reader = SidecarLibraryReader(root)
    result = {}
    for file_id in dict.fromkeys(file_ids):
        try:
            if reader.get_document(file_id) is None:
                continue
            obj = root / 'objects' / file_id
            path = reader.representation_path(file_id)
            if path.name == 'edited_text.json':
                # Segment overrides are JSON. Bound the parse; preserve the canonical
                # preview for very large override files instead of reading the corpus.
                if path.stat().st_size <= 2 * 1024 * 1024:
                    overrides = json.loads(path.read_text(encoding='utf-8'))
                    preview = '\n\n'.join(row.get('text','')[:1200] for row in overrides.get('segments',[])[:4])[:1200]
                else:
                    preview = _read_prefix(reader.representation_path(file_id,'canonical'),1200)
            else:
                preview = _read_prefix(path,1200)
            result[file_id] = {'text_preview':preview,
                'synthesis_preview':_read_prefix(reader._path('objects',file_id,'synth.txt'),1000)}
        except (ValueError, KeyError, json.JSONDecodeError):
            continue
    return result


def register_file_display_routes(app: FastAPI, *, store=None) -> None:
    if store is not None:
        from osii.server.auth import require
        reader_guard, writer_guard = require(), require('admin')
    else:
        def local_access():
            return {'role':'admin'}
        reader_guard = writer_guard = local_access

    def backend(request: Request):
        return store or getattr(request.app.state,'postgres_library',None)

    def load(request: Request):
        service = backend(request)
        if service is not None:
            return service.setting('file_display',{})
        path = request.app.state.osii_root.resolve() / 'state' / 'file-display.json'
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return {}

    @app.get('/api/files/display')
    def get_display(request: Request, actor=Depends(reader_guard)):
        return {'settings':display_settings(load(request)), 'can_manage':actor['role']=='admin'}

    @app.put('/api/files/display')
    def put_display(request: Request, payload: FileDisplay, actor=Depends(writer_guard)):
        value = payload.model_dump()
        service = backend(request)
        if service is not None:
            if store is not None:
                store.save_setting('file_display',value)
                store.record('file_display_changed',actor['id'],'shared')
            else:
                service.set_setting('file_display',value)
        else:
            from osii.domain.storage.atomic import atomic_write_text
            atomic_write_text(request.app.state.osii_root.resolve() / 'state' / 'file-display.json',json.dumps(value))
        return {'settings':value,'can_manage':True}

    @app.post('/api/files/previews')
    def previews(request: Request, payload: PreviewRequest, actor=Depends(reader_guard)):
        service = backend(request)
        if service is not None:
            return {'items':postgres_previews(service.engine,payload.file_ids)}
        return {'items':sidecar_previews(request.app.state.osii_root.resolve(),payload.file_ids)}
