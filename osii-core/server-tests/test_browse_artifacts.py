from conftest import document, login
from sqlalchemy import insert
from osii.persistence.workspace_schema import scope_products, scope_revisions


def test_folder_details_use_saved_bounded_synthesis(client, app, monkeypatch):
    store=app.state.store
    document(store, app.state.settings.source_root, name='nested/report.txt')
    with store.transaction() as c:
        c.execute(insert(scope_products).values(id='p',scope_type='folder',scope_id='nested',filename='summary.json',family='synthesis',method='test',current_revision='r',title='Folder title',artifact_type='text'))
        c.execute(insert(scope_revisions).values(id='r',product_id='p',origin='generated',created_at='2026-11-12',data={'text':'A'*1000},provenance={}))
    def forbidden(*args,**kwargs):raise AssertionError('Browse loaded document bodies or invoked a model')
    monkeypatch.setattr(store,'snapshot',forbidden)
    monkeypatch.setattr('osii.persistence.scope_products.ScopeProducts.history',forbidden)
    assert client.post('/api/scopes/artifacts',json={'scope':{'scope_type':'folder','folder_id':'nested'}}).status_code==401
    login(client,'reader')
    result=client.post('/api/scopes/artifacts',json={'scope':{'scope_type':'folder','folder_id':'nested'}})
    assert result.status_code==200
    assert result.json()['artifact_summary']['member_count']==1
    assert result.json()['artifact_summary']['synthesis_preview']=='A'*240
    assert not result.json()['actions']['can_synthesize']
    assert client.get('/api/catalog/files?direct=true').json()['total']==0
    assert client.get('/api/catalog/files?direct=true&folder_id=nested').json()['total']==1


def test_private_collection_artifacts_are_not_exposed(client, app):
    login(client)
    created=client.post('/api/collections',json={'name':'Private','members':[]})
    assert created.status_code==200
    identity=created.json()['id']
    login(client,'reader')
    result=client.post('/api/scopes/artifacts',json={'scope':{'scope_type':'collection','collection_id':identity}})
    assert result.status_code==422
    assert 'artifact_summary' not in result.json()
