"""Revision-checked preferred text editing over the shared PostgreSQL authoring service."""
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from osii.server.auth import require
from osii.domain.storage.text_authoring import PostgresTextAuthoring
from osii.domain.storage.authoring import AuthoringConflict


class Segment(BaseModel):
    id: str = Field(min_length=1, max_length=500)
    text: str = Field(max_length=2_000_000)


class EditVersion(BaseModel):
    expected_revision: str | None
    expected_extraction_id: str | None = Field(default=None, max_length=200)
    expected_state: str = Field(min_length=64, max_length=64)


class Edit(EditVersion):
    segments: list[Segment] = Field(min_length=1, max_length=100_000)


def register_text_routes(app, store):
    authoring = PostgresTextAuthoring(store.engine)

    def get(file_id):
        try: return authoring.get(file_id)
        except KeyError: raise HTTPException(404, "Document not found") from None

    @app.get('/api/objects/{file_id}/texts/canonical')
    def canonical(file_id: str, extraction_id: str | None = None, actor=Depends(require())):
        from osii.domain.read.postgres import PostgresLibraryReader
        value=PostgresLibraryReader(store.engine).get_representation(file_id, extraction_id or 'canonical')
        if value is None: raise HTTPException(404,'Extraction not found')
        return {'text':value.text,'segments':[{'id':row.segment_id,'kind':'text','path':'',
                'span':{'char_start':row.char_start,'char_end':row.char_end},'source_origin':row.source_origin} for row in value.segments]}

    @app.get('/api/objects/{file_id}/texts/edited')
    def edited(file_id: str, actor=Depends(require())):
        value = get(file_id)
        return {'file_id':file_id, 'exists':value.revision is not None, 'representation':'edited',
                'segments':value.segments, 'revision':value.revision, 'state_revision':value.state_revision}

    def write(file_id, payload, segments, actor):
        if segments is not None and sum(len(row['text']) for row in segments)>2_000_000:
            raise HTTPException(422, 'Edited text exceeds the 2,000,000-character limit')
        if segments is not None and any('\x00' in row['text'] for row in segments):
            raise HTTPException(422, 'Edited text cannot contain NUL characters')
        try:
            value=authoring.save(file_id,segments,expected_revision=payload.expected_revision,expected_state=payload.expected_state,expected_extraction_id=payload.expected_extraction_id)
        except KeyError: raise HTTPException(404,'Document not found') from None
        except AuthoringConflict as error: raise HTTPException(409,str(error)) from None
        store.record('document_text_restored' if segments is None else 'document_text_edited',actor['id'],file_id)
        return {'file_id':file_id,'representation':'edited','updated':segments is not None,'removed':segments is None,
                'segments':value.segments,'revision':value.revision,'state_revision':value.state_revision,
                'stale':{'embeddings':True,'search_chunks':False,'syntheses':True,'enrichments':True}}

    @app.put('/api/objects/{file_id}/texts/edited')
    def save(file_id: str, payload: Edit, actor=Depends(require('curator'))):
        return write(file_id,payload,[row.model_dump() for row in payload.segments],actor)

    @app.delete('/api/objects/{file_id}/texts/edited')
    def restore(file_id: str, payload: EditVersion, actor=Depends(require('curator'))):
        return write(file_id,payload,None,actor)
