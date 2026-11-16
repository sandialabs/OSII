import json
import numpy as np
import pytest
from osii.domain.collection_suggestions import topic_proposals, guided_proposals, SuggestionModelError


def corpus(per_topic=8):
    topics=['garden soil vegetable compost seed','forest timber tree conservation woodland','music piano orchestra symphony composer']
    docs=[{'file_id':f'{g}-{i:04}', 'filename':f'opaque-{g}-{i}.pdf','source_relpath':'same-folder/random.pdf',
        'text_preview':(words+' ')*10,'synthesis_preview':words} for g,words in enumerate(topics) for i in range(per_topic)]
    docs.append({'file_id':'outlier','filename':'odd.pdf','source_relpath':'same-folder/odd.pdf',
        'text_preview':'unique spacecraft orbital astronomy lunar galaxy'})
    return docs


def test_starters_are_distinct_coherent_deterministic_and_leave_outliers():
    docs=corpus()
    result=topic_proposals(docs)
    assert len(result)==3
    assert result==topic_proposals(list(reversed(docs)))
    assert {tuple(sorted({fid.split('-')[0] for fid in item['file_ids']})) for item in result} == {('0',),('1',),('2',)}
    assert all(2<=len(item['file_ids'])<=100 for item in result)
    assert all('outlier' not in item['file_ids'] for item in result)
    assert all(len(item['documents'])==len(item['file_ids']) and item['keywords'] for item in result)
    assert all(item['method']=='saved-text' for item in result)


def test_every_catalog_document_can_contribute_beyond_one_thousand():
    docs=corpus(400)
    result=topic_proposals(docs)
    assert len(result)>=3
    assert any(any(fid.startswith('2-') for fid in item['file_ids']) for item in result)
    assert sum(len(item['file_ids']) for item in result)<len(docs)


def test_saved_vectors_group_without_projecting_and_do_not_duplicate_text_topics():
    docs=corpus()[:-1]
    vectors=np.array([[1,0,0]]*8+[[0,1,0]]*8+[[0,0,1]]*8,dtype=np.float32)
    result=topic_proposals(docs,docs,vectors)
    assert len(result)==3
    assert all(item['method']=='saved-embeddings' for item in result)


def test_noise_and_singletons_do_not_become_collections():
    assert topic_proposals([])==[]
    assert topic_proposals([{'file_id':'one','filename':'1.pdf'}])==[]
    assert topic_proposals([{'file_id':str(i),'filename':'0000.pdf','text_preview':'the and of page copyright'} for i in range(20)])==[]


def test_prompt_is_bounded_and_can_only_choose_known_candidates():
    docs=corpus(80)
    calls=[]
    def complete(messages):
        calls.append(messages)
        manifest=json.loads(messages[1]['content'])
        assert len(manifest['documents'])<=96
        assert manifest['goal']=='Focus on forest conservation'
        assert all(len(row['summary'])<=420 for row in manifest['documents'])
        return json.dumps({'collections':[{'name':'Conservation','description':'A proposed reading group','document_ids':[0,1]}]})
    result,count=guided_proposals(docs,'Focus on forest conservation',complete,topic_proposals(docs,limit=12))
    assert len(calls)==1 and count==96
    assert len(result)==1 and result[0]['method']=='ai-guided'
    assert all(fid.startswith('1-') for fid in result[0]['file_ids'])
    assert all(row['file_id'] in {doc['file_id'] for doc in docs} for row in result[0]['documents'])


@pytest.mark.parametrize('response',[
    {'collections':[{'name':'Invented','document_ids':[0,9999]}]},
    {'collections':[{'name':'Wrong types','document_ids':[True,False]}]},
    {'collections':[{'name':'Only one','document_ids':[0,0]}]},
    {'collections':[{'name':'','document_ids':[0,1]}]},
])
def test_invalid_model_memberships_are_rejected(response):
    with pytest.raises(SuggestionModelError):
        guided_proposals(corpus(),'gardening',lambda messages:json.dumps(response),[])


def test_sidecar_http_suggestions_use_saved_data_and_persist_no_collections(tmp_path,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from osii.api.collection_suggestion_routes import register_collection_suggestion_routes
    root=tmp_path/'library'
    for doc in corpus()[:-1]:
        obj=root/'objects'/doc['file_id'];obj.mkdir(parents=True)
        (obj/'meta.toml').write_text('[file]\nfilename="'+doc['filename']+'"\nsource_relpath="'+doc['source_relpath']+'"\nmime="text/plain"\n[hash]\nsha256="'+doc['file_id']+'"\n')
        (obj/'text.txt').write_text(doc['text_preview'])
        (obj/'provenance.toml').write_text('[provenance]\nstatus="done"\n')
    app=FastAPI();app.state.osii_root=root
    register_collection_suggestion_routes(app)
    with TestClient(app) as client:
        result=client.get('/api/collection-suggestions')
        assert result.status_code==200,result.text
        assert len(result.json()['suggestions'])==3
        assert result.json()['considered_documents']==24
        assert not list((root/'collections').glob('*/collection.toml'))
        assert (root/'cache'/'collection-suggestions.json').exists()
        assert client.post('/api/collection-suggestions',json={'prompt':' '}).status_code==422


def test_shared_sidecar_imports_do_not_require_postgres_dependencies():
    import subprocess,sys
    script = """
import builtins
normal=builtins.__import__
def guarded(name,*args,**kwargs):
    if name.startswith('sqlalchemy'):
        raise AssertionError('Sidecar suggestions unexpectedly require PostgreSQL dependencies')
    return normal(name,*args,**kwargs)
builtins.__import__=guarded
import osii.api.collection_suggestion_routes
"""
    subprocess.run([sys.executable,'-c',script],check=True)
