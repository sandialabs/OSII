import json
from fastapi import FastAPI
from fastapi.testclient import TestClient
from osii.api.file_display_routes import register_file_display_routes


def application(root):
    app = FastAPI()
    app.state.osii_root = root
    register_file_display_routes(app)
    return TestClient(app)


def test_local_display_defaults_persist_per_library(tmp_path):
    client = application(tmp_path/'first')
    assert client.get('/api/files/display').json()['can_manage']
    settings = {'view':'list','show_name':False,'show_size':True,'metadata':'path'}
    assert client.put('/api/files/display',json=settings).status_code == 200
    assert application(tmp_path/'first').get('/api/files/display').json()['settings'] == settings
    assert application(tmp_path/'second').get('/api/files/display').json()['settings']['show_name']
    assert client.put('/api/files/display',json={**settings,'metadata':'unknown'}).status_code == 422


def test_sidecar_preview_is_bounded_and_never_reads_originals(tmp_path):
    obj = tmp_path/'objects'/'known'
    obj.mkdir(parents=True)
    (obj/'meta.toml').write_text('[file]\nfilename="report.txt"\nsource_relpath="missing-original.txt"\nmime="text/plain"\n[hash]\nsha256="abc"\n')
    (obj/'text.txt').write_text('T'*300000)
    (obj/'synth.txt').write_text('S'*300000)
    client = application(tmp_path)
    response = client.post('/api/files/previews',json={'file_ids':['known','missing','../outside']})
    assert response.status_code == 200
    assert set(response.json()['items']) == {'known'}
    preview = response.json()['items']['known']
    assert preview['text_preview'] == 'T'*1200
    assert preview['synthesis_preview'] == 'S'*1000
    (obj/'edited_text.json').write_text(json.dumps({'segments':[{'id':'page-1','text':'Human corrected text'}]}))
    assert client.post('/api/files/previews',json={'file_ids':['known']}).json()['items']['known']['text_preview'] == 'Human corrected text'
    assert client.post('/api/files/previews',json={'file_ids':['known']*49}).status_code == 422
