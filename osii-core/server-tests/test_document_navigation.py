from conftest import document, login
from sqlalchemy import insert, update

from osii.persistence.postgres import artifacts, documents, extractions
from osii.persistence.workspace_schema import scope_products, scope_revisions


def test_document_navigation_reads_headers_without_loading_bodies(client, app, monkeypatch):
    store = app.state.store
    doc = document(store, app.state.settings.source_root)
    identity = doc['file_id']
    with store.transaction() as connection:
        connection.execute(update(extractions).where(extractions.c.file_id == identity).values(
            response={'processor': {'name': 'OCR', 'version': '1'},
                'segments': [{'text': 'PRIVATE EXTRACTION BODY' * 1000}],
                'artifacts': [{'id': 'boxes', 'standard_data': {'artifact_type': 'table', 'rows': []}}]}))
        connection.execute(insert(artifacts).values(id='wiki', file_id=identity, kind='enrichment', payload={
            'response': {'processor': {'display_name': 'Reference'}, 'artifacts': [
                {'standard_data': {'artifact_type': 'wiki_markdown', 'markdown': 'PRIVATE BODY' * 1000}}
            ]}}))
        connection.execute(insert(scope_products).values(id='p', scope_type='object', scope_id=identity,
            filename='summary.json', family='synthesis', method='test', current_revision='r',
            title='Saved summary', artifact_type='text'))
        connection.execute(insert(scope_revisions).values(id='r', product_id='p', origin='generated',
            created_at='2026-11-13', data={'artifact_type': 'text', 'text': 'Saved body'}, provenance={}))

    def forbidden(*args, **kwargs):
        raise AssertionError('Document navigation loaded a complete document')

    monkeypatch.setattr(store, 'snapshot', forbidden)
    monkeypatch.setattr(store, 'document', forbidden)
    for suffix in ('?summary=true', '/extractions/catalog', '/products/catalog', '/products/wiki'):
        assert client.get(f'/api/objects/{identity}{suffix}').status_code == 401
    login(client, 'reader')
    header = client.get(f'/api/objects/{identity}?summary=true')
    assert header.status_code == 200
    assert set(header.json()) == {'file_id', 'filename', 'source_relpath', 'media_type'}
    versions = client.get(f'/api/objects/{identity}/extractions/catalog')
    assert versions.status_code == 200, versions.text
    assert len(versions.json()['items']) == 1
    version = versions.json()['items'][0]
    assert version['primary'] and version['segment_count'] == 1
    assert 'response' not in version and 'text' not in version
    products = client.get(f'/api/objects/{identity}/products/catalog')
    assert products.status_code == 200, products.text
    assert 'PRIVATE BODY' not in products.text and 'Saved body' not in products.text
    assert {row['id'] for row in products.json()['items']} == {'wiki', 'product:p', 'extraction:' + version['id']}
    extraction = client.get(f'/api/objects/{identity}/products/extraction:{version["id"]}')
    assert extraction.status_code == 200
    assert extraction.json()['payload']['response']['artifacts'][0]['id'] == 'boxes'
    assert 'PRIVATE EXTRACTION BODY' not in extraction.text
    assert products.json()['items'][0]['types'] == ['wiki_markdown']
    assert client.get(f'/api/objects/{identity}/products/wiki').json()['payload']['response']['artifacts']
    assert client.get(f'/api/objects/{identity}/products/product:p').json()['payload']['data']['text'] == 'Saved body'


def test_product_previews_are_document_scoped_and_bounded(client, app):
    store = app.state.store
    first = document(store, app.state.settings.source_root, name='one.txt')['file_id']
    second = document(store, app.state.settings.source_root, name='two.txt', content='Different source text.')['file_id']
    with store.transaction() as connection:
        connection.execute(insert(artifacts).values(id='huge', file_id=first, kind='synthesis',
            payload={'response': {'markdown': 'X' * 4_194_305}}))
        connection.execute(insert(artifacts).values(id='normal', file_id=first, kind='synthesis',
            payload={'response': {'markdown': 'Summary'}}))
    login(client, 'reader')
    assert client.get(f'/api/objects/{first}/products/normal').status_code == 200
    assert client.get(f'/api/objects/{second}/products/normal').status_code == 404
    assert client.get(f'/api/objects/{first}/products/huge').status_code == 404
    assert len(client.get(f'/api/objects/{first}/products/catalog').content) < 1500
    with store.transaction() as connection:
        connection.execute(update(documents).where(documents.c.file_id == first).values(active=False))
    for suffix in ('?summary=true', '/extractions/catalog', '/products/catalog', '/products/normal'):
        assert client.get(f'/api/objects/{first}{suffix}').status_code == 404
