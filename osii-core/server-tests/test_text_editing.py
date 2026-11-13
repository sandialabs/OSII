from conftest import document, login
from sqlalchemy import select,update
from osii.persistence.postgres import documents, chunks


def test_edit_restore_search_and_conflicts(client,app):
    store=app.state.store;doc=document(store,app.state.settings.source_root)
    file_id=doc['file_id'];path=f'/api/objects/{file_id}/texts/edited'
    assert client.get(path).status_code==401
    login(client,'reader');version=client.get(path).json()
    canonical=client.get(f'/api/objects/{file_id}/texts/canonical').json()
    segment=canonical['segments'][0]['id']
    payload={'expected_revision':version['revision'],'expected_state':version['state_revision'],'segments':[{'id':segment,'text':'Unique corrected wording clarifies the instrument.'}]}
    assert client.put(path,json=payload).status_code==403
    login(client,'curator')
    csrf=client.headers.pop('X-CSRF-Token');assert client.put(path,json=payload).status_code==403;client.headers['X-CSRF-Token']=csrf
    assert client.put(path,json={**payload,'expected_extraction_id':'different-extraction'}).status_code==409
    payload['expected_extraction_id']=store.extraction_records(file_id)[0]['id']
    result=client.put(path,json=payload);assert result.status_code==200
    assert client.put(path,json=payload).status_code==409
    assert client.get(f'/api/objects/{file_id}/texts/preferred').json()['text'].startswith('Unique corrected')
    with store.engine.connect() as connection:
        assert connection.execute(select(documents.c.text).where(documents.c.file_id==file_id)).scalar()==doc['text']
        rows=connection.execute(select(chunks).where(chunks.c.file_id==file_id)).mappings().all()
        assert rows and all(row['embedding'] is None for row in rows)
        assert all(not row['source_origin'].get('page') for row in rows)
    assert client.post('/api/search',json={'query':'corrected wording','mode':'lexical'}).json()['results']
    version=client.get(path).json()
    restored=client.request('DELETE',path,json={'expected_revision':version['revision'],'expected_state':version['state_revision']})
    assert restored.status_code==200
    assert client.get(f'/api/objects/{file_id}/texts/preferred').json()['text']==doc['text']
    assert client.put(path,json=payload).status_code==409
    version=client.get(path).json();payload.update(expected_revision=version['revision'],expected_state=version['state_revision'])
    with store.transaction() as connection:
        current=connection.execute(select(documents.c.metadata).where(documents.c.file_id==file_id)).scalar()
        connection.execute(update(documents).where(documents.c.file_id==file_id).values(metadata={**current,'primary_extraction_id':'replacement'}))
    assert client.put(path,json=payload).status_code==409


def test_unknown_segments_and_empty_payloads_fail(client,app):
    doc=document(app.state.store,app.state.settings.source_root);path=f"/api/objects/{doc['file_id']}/texts/edited"
    login(client)
    version=client.get(path).json()
    assert client.put(path,json={'segments':[]}).status_code==422
    result=client.put(path,json={'expected_revision':None,'expected_state':version['state_revision'],'segments':[{'id':'unknown','text':'invented'}]})
    assert result.status_code==422
    assert not client.get(path).json()['exists']


def test_new_synthesis_uses_edits_and_marks_earlier_products_stale(client,app):
    from test_derived_processing import create_plan, start
    from test_intake_plans import execute
    store=app.state.store;doc=document(store,app.state.settings.source_root);file_id=doc['file_id']
    def synthesize():
        job=create_plan(app,[doc['source_relpath']],synthesizer_name='local.extractive-preview')
        start(app,job);run=execute(app,job);assert run['status']=='done',run['logs']
    synthesize()
    login(client)
    path=f'/api/objects/{file_id}/texts/edited';version=client.get(path).json()
    canonical=client.get(f'/api/objects/{file_id}/texts/canonical').json()
    assert client.put(path,json={'expected_revision':version['revision'],'expected_state':version['state_revision'],
        'segments':[{'id':canonical['segments'][0]['id'],'text':'Curator correction changes the preferred detector description.'}]}).status_code==200
    assert all(row['stale'] for row in client.get(f'/api/objects/{file_id}/artifacts').json()['items'])
    synthesize()
    artifacts=client.get(f'/api/objects/{file_id}/artifacts').json()['items']
    current=[row for row in artifacts if not row['stale']]
    assert len(current)==1
    assert 'Curator correction' in current[0]['payload']['response']['markdown']
