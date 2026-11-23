from conftest import document, login
from sqlalchemy import insert, update
from osii.persistence.postgres import artifacts, documents
from osii.server.api import create_app


def test_library_defaults_require_admin_and_persist_across_app_instances(client, app):
    assert client.get('/api/files/display').status_code == 401
    login(client, 'reader')
    result = client.get('/api/files/display').json()
    assert result['settings']['view'] == 'thumbnails'
    assert not result['can_manage']
    settings = {'view':'list','show_name':False,'show_size':True,'metadata':'format'}
    assert client.put('/api/files/display', json=settings).status_code == 403
    login(client, 'curator')
    assert client.put('/api/files/display', json=settings).status_code == 403
    login(client)
    csrf = client.headers.pop('X-CSRF-Token')
    assert client.put('/api/files/display', json=settings).status_code == 403
    client.headers['X-CSRF-Token'] = csrf
    assert client.put('/api/files/display', json={**settings,'show_name':'false'}).status_code == 422
    assert client.put('/api/files/display', json={**settings,'extra':'not supported'}).status_code == 422
    assert client.put('/api/files/display', json=settings).status_code == 200
    from fastapi.testclient import TestClient
    restarted = create_app(app.state.settings, app.state.store)
    with TestClient(restarted) as other:
        login(other, 'reader')
        assert other.get('/api/files/display').json()['settings'] == settings


def test_preview_batches_are_bounded_and_use_saved_synthesis(client, app, monkeypatch):
    store = app.state.store
    doc = document(store, app.state.settings.source_root)
    identity = doc['file_id']
    with store.transaction() as connection:
        connection.execute(update(documents).where(documents.c.file_id==identity).values(text='T'*300000))
        connection.execute(insert(artifacts).values(id='summary',file_id=identity,kind='synthesis',payload={
            'created_at':'2026-11-14','response':{'markdown':'S'*300000}}))
    def forbidden(*args, **kwargs):
        raise AssertionError('Tile previews must not materialize the corpus or call a model')
    monkeypatch.setattr(store,'snapshot',forbidden)
    monkeypatch.setattr(store,'document',forbidden)
    assert client.post('/api/files/previews',json={'file_ids':[identity]}).status_code == 401
    login(client, 'reader')
    result = client.post('/api/files/previews',json={'file_ids':[identity,'missing']})
    assert result.status_code == 200, result.text
    assert len(result.content) < 2600
    assert result.json()['items'][identity]['text_preview'] == 'T'*1200
    assert result.json()['items'][identity]['synthesis_preview'] == 'S'*1000
    assert 'missing' not in result.json()['items']
    assert client.post('/api/files/previews',json={'file_ids':[identity]*49}).status_code == 422
    with store.transaction() as connection:
        connection.execute(update(documents).where(documents.c.file_id==identity).values(active=False))
    assert client.post('/api/files/previews',json={'file_ids':[identity]}).json()['items'] == {}


def test_collection_append_is_idempotent_and_enforces_owner(client, app):
    identity = document(app.state.store,app.state.settings.source_root)['file_id']
    login(client, 'reader')
    collection = client.post('/api/collections',json={'name':'Mine','members':[]}).json()
    path = f'/api/collections/{collection["id"]}/members'
    for _ in range(2):
        assert client.post(path,json={'file_ids':[identity]}).status_code == 200
    assert client.get('/api/collections').json()['items'][0]['members'] == [identity]
    login(client, 'curator')
    assert client.post(path,json={'file_ids':[identity]}).status_code == 404
