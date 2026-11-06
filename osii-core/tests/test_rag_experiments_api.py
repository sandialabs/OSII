"""Local profile selection and fair, bounded comparisons without model calls."""
import json

import pytest
pytest.importorskip("haystack")

from osii.rag.config import get_chat_settings
from osii.rag.models import ChatRequest, ScopeModel
from osii.rag.strategies import RankedEvidence
from osii.rag.strategies.profiles import get_profile


@pytest.fixture(autouse=True)
def isolated_chat_model(monkeypatch, temp_osii_root):
    from dataclasses import replace
    settings = replace(get_chat_settings(temp_osii_root), chat_provider_chain=("extractive",))
    monkeypatch.setattr("osii.rag.local_experiments.get_chat_settings", lambda root: settings)
    monkeypatch.setattr("osii.rag.local_experiments.complete_experiment_messages",
                        lambda **kwargs: pytest.fail("A test must explicitly provide its model adapter"))


def indexed(root):
    path=root/'embeddings/chunks/chunks.jsonl'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(''.join(json.dumps({**row, 'text': row['snippet'], 'source_text_representation': 'canonical'}) + '\n' for row in hits()))
    return path


def hits():
    return [dict(file_id="a",chunk_id="a:0",filename="one.pdf",source_relpath="one.pdf",snippet="First grounded excerpt",char_start=0,char_end=22,source_origin={"page":1,"bbox":[0.1,0.2,0.3,0.4]}),
            dict(file_id="b",chunk_id="b:0",filename="two.pdf",source_relpath="two.pdf",snippet="The calibration source is 241Am.",char_start=0,char_end=31,source_origin={"page":2})]


def test_profiles_and_empty_experiment_make_no_model_calls(client,monkeypatch):
    def forbidden(**kwargs): pytest.fail("Empty libraries must not invoke chat")
    monkeypatch.setattr("osii.rag.local_experiments.complete_experiment_messages",forbidden)
    catalog=client.get('/api/chat/profiles').json()
    assert {p['id'] for p in catalog['profiles']} == {'lexical-v1','hybrid-v1','hybrid-reranked-v1','iterative-v1'}
    assert not next(p for p in catalog['profiles'] if p['id']=='hybrid-reranked-v1')['available']
    r=client.post('/api/chat',json={'query':'question','scope':{'scope_type':'root'},'profile_id':'lexical-v1'})
    assert r.status_code==200,r.text
    result=r.json()
    assert result['experiment']['chat_calls']==0 and result['experiment']['result']['stop_reason']=='abstained'
    assert result['experiment']['warnings'] and not result['citations']


def test_comparison_holds_settings_and_scope_and_does_not_write_index(client,temp_osii_root,monkeypatch):
    manifest=indexed(temp_osii_root); original=manifest.read_bytes(); seen=[]
    def search(root,**kwargs):
        seen.append(kwargs);return 'lexical',hits()
    monkeypatch.setattr('osii.rag.local_experiments.dashboard_search',search)
    r=client.post('/api/chat/compare',json={'query':'source?','scope':{'scope_type':'object','file_id':'b'},'profile_ids':['lexical-v1','hybrid-v1']})
    assert r.status_code==200,r.text
    result=r.json()
    assert [call['mode'] for call in seen]==['lexical','hybrid']
    assert all(call['scope']['file_id']=='b' for call in seen)
    for run in result['runs']:
        response=run['response']; trace=response['experiment']
        assert {e['file_id'] for e in trace['result']['evidence']}=={'b'}
        assert response['citations'][0]['source_origin']['page']==2
        assert trace['chat_calls']==0 and trace['corpus_check']==result['corpus_check']
    assert result['runs'][1]['response']['experiment']['warnings']
    assert manifest.read_bytes()==original


def test_reranker_is_a_core_hook_and_its_order_scores_and_geometry_are_traced(client,test_app,temp_osii_root,monkeypatch):
    indexed(temp_osii_root)
    monkeypatch.setattr('osii.rag.local_experiments.dashboard_search',lambda *a,**k: ('hybrid',hits()))
    seen=[]
    def rerank(request):
        seen.append(request)
        return [RankedEvidence(e.id,100 if e.file_id=='b' else 0) for e in request.candidates]
    monkeypatch.setattr(test_app.state,'rag_reranker',rerank,raising=False)
    r=client.post('/api/chat',json={'query':'q','scope':{'scope_type':'root'},'profile_id':'hybrid-reranked-v1'})
    assert r.status_code==200,r.text
    trace=r.json()['experiment']
    assert seen and trace['reranker_calls']==1
    assert trace['retrieval'][0]['ranking'][0]['score']==100
    assert trace['result']['evidence'][0]['file_id']=='b'
    assert r.json()['citations'][1]['source_origin']['bbox']==[0.1,0.2,0.3,0.4]


def test_invalid_and_unavailable_profiles_do_not_invoke_generation(client,monkeypatch):
    monkeypatch.setattr('osii.rag.local_experiments.complete_experiment_messages',lambda **k: pytest.fail('unexpected model call'))
    for profile in ('not-a-profile','hybrid-reranked-v1','iterative-v1'):
        r=client.post('/api/chat',json={'query':'q','scope':{'scope_type':'root'},'profile_id':profile})
        assert r.status_code==422,r.text
    r=client.post('/api/chat/compare',json={'query':'q','scope':{'scope_type':'root'},'profile_ids':['lexical-v1','lexical-v1']})
    assert r.status_code==422
    r=client.post('/api/chat',json={'query':'q','scope':{'scope_type':'folder','folder_id':'missing'},'profile_id':'lexical-v1'})
    assert r.status_code==422 and 'broaden' in r.text


def test_index_change_aborts_comparison_instead_of_returning_mixed_results(client,temp_osii_root,monkeypatch):
    manifest=indexed(temp_osii_root)
    def search(*a,**kw):
        manifest.write_text('changed index')
        return 'lexical',hits()
    monkeypatch.setattr('osii.rag.local_experiments.dashboard_search',search)
    r=client.post('/api/chat/compare',json={'query':'q','scope':{'scope_type':'root'},'profile_ids':['lexical-v1','hybrid-v1']})
    assert r.status_code==409,r.text


def test_iterative_chat_follows_query_with_same_configured_model_and_no_fallback(client,temp_osii_root,monkeypatch):
    from dataclasses import replace
    indexed(temp_osii_root)
    settings=replace(get_chat_settings(temp_osii_root),chat_provider_chain=('openai','extractive'),openai_chat_model='gemma4')
    monkeypatch.setattr('osii.rag.local_experiments.get_chat_settings',lambda root: settings)
    queries=[];models=[]
    def search(*a,**kw):
        queries.append(kw['query']);return 'hybrid',hits()[:1] if len(queries)==1 else hits()
    def completion(**kw):
        models.append(kw['model'])
        context=json.loads(kw['messages'][1]['content'])
        if len(models)==1: value={'action':'retrieve','query':'calibration isotope'}
        else:value={'action':'answer','answer':'241Am','citation_ids':[e['id'] for e in context['evidence'] if e['file_id']=='b']}
        return json.dumps(value),{'prompt_tokens':10,'completion_tokens':5},'gemma4'
    monkeypatch.setattr('osii.rag.local_experiments.dashboard_search',search)
    monkeypatch.setattr('osii.rag.local_experiments.complete_experiment_messages',completion)
    r=client.post('/api/chat',json={'query':'Which source?','scope':{'scope_type':'root'},'profile_id':'iterative-v1'})
    assert r.status_code==200,r.text
    assert queries==['Which source?','calibration isotope'] and models==['gemma4','gemma4']
    assert r.json()['experiment']['chat_calls']==2 and r.json()['citations'][0]['file_id']=='b'


def test_compare_preserves_partial_mode_failure_and_has_no_provider_fallback(client,temp_osii_root,monkeypatch):
    from dataclasses import replace
    indexed(temp_osii_root)
    settings=replace(get_chat_settings(temp_osii_root),chat_provider_chain=('openai','extractive'),openai_chat_model='chosen-model')
    monkeypatch.setattr('osii.rag.local_experiments.get_chat_settings',lambda root: settings)
    monkeypatch.setattr('osii.rag.local_experiments.dashboard_search',lambda *a,**k:('lexical',hits()))
    calls=[]
    def completion(**kw):
        calls.append(kw['provider'])
        if len(calls)==1:return 'invalid JSON',{},'chosen-model'
        ctx=json.loads(kw['messages'][1]['content'])
        return json.dumps({'action':'answer','answer':'Evidence','citation_ids':[ctx['evidence'][0]['id']]}),{},'chosen-model'
    monkeypatch.setattr('osii.rag.local_experiments.complete_experiment_messages',completion)
    r=client.post('/api/chat/compare',json={'query':'q','scope':{'scope_type':'root'},'profile_ids':['lexical-v1','hybrid-v1']})
    assert r.status_code==200,r.text
    assert [run['status'] for run in r.json()['runs']]==['error','ok'] and calls==['openai','openai']


def test_experiments_use_full_indexed_passages_instead_of_display_snippets(client,temp_osii_root,monkeypatch):
    manifest=indexed(temp_osii_root)
    text='Introductory text. ' * 40 + 'The answer appears after the display preview.'
    row={**hits()[0], 'snippet':text[:400], 'char_end':len(text)}
    manifest.write_text(json.dumps({**row, 'text':text, 'source_text_representation':'canonical', 'source_extraction_id':'ocr-1'})+'\n')
    monkeypatch.setattr('osii.rag.local_experiments.dashboard_search',lambda *a,**k:('lexical',[row]))
    r=client.post('/api/chat',json={'query':'q','scope':{'scope_type':'root'},'profile_id':'lexical-v1'})
    assert r.status_code==200,r.text
    evidence=r.json()['experiment']['result']['evidence'][0]
    assert evidence['text']==text and evidence['char_end']==len(text)
    assert evidence['representation']=='canonical:ocr-1'
    assert text in r.json()['answer']


def test_each_comparison_mode_performs_its_own_retrieval(client,temp_osii_root,monkeypatch):
    from dataclasses import replace
    indexed(temp_osii_root)
    settings=replace(get_chat_settings(temp_osii_root),chat_provider_chain=('openai',),openai_chat_model='chosen-model')
    monkeypatch.setattr('osii.rag.local_experiments.get_chat_settings',lambda root: settings)
    def completion(**kw):
        ctx=json.loads(kw['messages'][1]['content'])
        return json.dumps({'action':'answer','answer':'Evidence','citation_ids':[ctx['evidence'][0]['id']]}),{},'chosen-model'
    monkeypatch.setattr('osii.rag.local_experiments.complete_experiment_messages',completion)
    seen=[]
    def search(*a,**kw):
        seen.append(kw['mode']); return 'hybrid',hits()
    monkeypatch.setattr('osii.rag.local_experiments.dashboard_search',search)
    r=client.post('/api/chat/compare',json={'query':'q','scope':{'scope_type':'root'},'profile_ids':['hybrid-v1','iterative-v1']})
    assert r.status_code==200,r.text
    assert seen==['hybrid','hybrid']


def test_keyword_profile_reads_real_indexed_text_and_preserves_it(client,temp_osii_root,sample_osii_object):
    from osii.domain.storage.objects import write_text_file
    from osii.indexing.chunking import write_chunk_manifest
    text='Calibration uses a reference. ' * 25 + 'The isotope is americium.'
    write_text_file(temp_osii_root,sample_osii_object['file_id'],text)
    manifest,_=write_chunk_manifest(temp_osii_root,method='paragraph')
    before=manifest.read_bytes()
    r=client.post('/api/chat',json={'query':'americium','scope':{'scope_type':'root'},'profile_id':'lexical-v1'})
    assert r.status_code==200,r.text
    evidence=r.json()['experiment']['result']['evidence']
    assert len(evidence)==1 and evidence[0]['text']==text
    assert evidence[0]['char_end']==len(text) and 'americium' in r.json()['answer']
    assert manifest.read_bytes()==before
