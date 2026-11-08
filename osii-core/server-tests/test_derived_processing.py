import threading
from datetime import timedelta
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from conftest import Provider, document, login
from test_intake_plans import execute
from osii.persistence.postgres import now, settings as settings_table
from osii.server.intake import plan, configuration_stamp
from osii.server import processors
from osii.server.processor_gateway import grant, grant_id
from osii.processor_sdk import (Capability, ProcessorDescriptor, ProcessorKind, EnrichmentResponse, Artifact,
    ExtractionResponse, TextSegment)


def create_plan(app, paths, **options):
    store=app.state.store
    payload=plan(store,app.state.settings,paths,operation='process',embed=False,**options)
    return store.enqueue('plan',payload,status='staged')


def start(app,jid):
    app.state.store.control_job(jid,'start',configuration_stamp(app.state.store,app.state.settings))


def test_baselines_stage_then_process_without_models_or_extraction(client,app):
    store=app.state.store
    doc=document(store,app.state.settings.source_root)
    original=store.document(doc['file_id'])
    chunks=store.document_chunks(doc['file_id'])
    history=store.extraction_records(doc['file_id'])
    login(client)
    body={'paths':[doc['source_relpath']], 'operation':'process', 'synthesizer_name':'local.extractive-preview','enricher_name':'local.stats-keywords'}
    result=client.post('/api/admin/intake/stage',json=body)
    assert result.status_code==200,result.text
    jid=result.json()['id']
    assert result.json()['operations']['synthesize']=='Cited source-excerpt preview (no AI)'
    assert store.list_artifacts(doc['file_id'])==[]
    start(app,jid)
    run=execute(app,jid)
    assert run['status']=='done',run['logs']
    rows=store.list_artifacts(doc['file_id'])
    assert {row['kind'] for row in rows}=={'synthesis','enrichment'}
    assert all(row['payload']['input_extraction_id']==history[0]['id'] for row in rows)
    assert store.document(doc['file_id'])==original
    assert store.document_chunks(doc['file_id'])==chunks
    assert store.extraction_records(doc['file_id'])==history
    assert run['payload']['items'][0]['steps']=={'synthesis':'done','enrichment':'done'}
    login(client,'reader')
    assert all(not row['stale'] for row in client.get(f"/api/objects/{doc['file_id']}/artifacts").json()['items'])


def test_retry_preserves_successful_model_synthesis(app,monkeypatch):
    store=app.state.store
    doc=document(store,app.state.settings.source_root)
    store.save_configuration({'chat_model':'selected-chat'})
    jid=create_plan(app,[doc['source_relpath']],synthesizer_name='openai.synthesizer',enricher_name='local.stats-keywords')
    class Spy(Provider):
        calls=0
        def chat(self,model,messages,max_tokens=900):
            assert model=='selected-chat'
            self.calls+=1
            return 'Source-grounded generated synthesis.',{'completion_tokens':4}
    spy=Spy()
    target=processors.BUILTINS['local.stats-keywords']
    original=target.enrich
    attempts=[]
    def flaky(request):
        attempts.append(1)
        if len(attempts)==1: raise processors.ProcessorError('Synthetic enrichment failure')
        return original(request)
    monkeypatch.setattr(target,'enrich',flaky)
    start(app,jid)
    assert execute(app,jid,provider=spy)['status']=='error'
    assert spy.calls==1 and len(store.list_artifacts(doc['file_id']))==1
    store.control_job(jid,'retry',configuration_stamp(store,app.state.settings))
    assert execute(app,jid,provider=spy)['status']=='done'
    assert spy.calls==1 and len(store.list_artifacts(doc['file_id']))==2


def test_pause_during_model_call_finishes_all_steps_for_current_file(app):
    store=app.state.store;root=app.state.settings.source_root
    a=document(store,root,name='a.txt',content='First neutron report')
    b=document(store,root,name='b.txt',content='Second neutron report')
    store.save_configuration({'chat_model':'selected-chat'})
    jid=create_plan(app,[a['source_relpath'],b['source_relpath']],synthesizer_name='openai.synthesizer',enricher_name='local.stats-keywords')
    stamp=configuration_stamp(store,app.state.settings)
    class Pausing(Provider):
        calls=0
        def chat(self,*args,**kwargs):
            self.calls+=1
            if self.calls==1: store.control_job(jid,'pause',stamp)
            return 'Synthetic synthesis',{}
    provider=Pausing();start(app,jid)
    run=execute(app,jid,provider=provider)
    assert run['status']=='paused'
    assert run['payload']['items'][0]['steps']=={'synthesis':'done','enrichment':'done'}
    assert len(store.list_artifacts(a['file_id']))==2 and not store.list_artifacts(b['file_id'])
    store.control_job(jid,'resume',stamp)
    assert execute(app,jid,provider=provider)['status']=='done'
    assert provider.calls==2


def test_reextraction_preserves_derived_history_and_marks_stale(client,app):
    from osii.server.worker import ingest_file
    store=app.state.store;root=app.state.settings.source_root
    doc=document(store,root)
    jid=create_plan(app,[doc['source_relpath']],synthesizer_name='local.extractive-preview')
    start(app,jid);assert execute(app,jid)['status']=='done'
    class Extractor:
        def extract(self,request):
            old=store.extraction_records(doc['file_id'])[0]['response']
            return ExtractionResponse(request_id=request.request_id,processor=old['processor'],segments=[TextSegment(id='new',text='Improved canonical extraction')])
    ingest_file(store,Provider(),Extractor(),root,root/doc['source_relpath'],force=True)
    login(client,'reader')
    rows=client.get(f"/api/objects/{doc['file_id']}/artifacts").json()['items']
    assert len(rows)==1 and rows[0]['stale']
    assert 'neutron' in rows[0]['payload']['response']['markdown']


def test_invalid_options_and_auth_do_not_invoke_processors(client,app):
    doc=document(app.state.store,app.state.settings.source_root)
    for role in ('reader','curator'):
        login(client,role)
        assert client.get('/api/admin/processors').status_code==403
        assert client.put('/api/admin/processors',json={'urls':[]}).status_code==403
    login(client)
    body={'paths':[doc['source_relpath']],'operation':'process','synthesizer_name':'openai.synthesizer'}
    assert client.post('/api/admin/intake/stage',json=body).status_code==422
    body.update(synthesizer_name=None,enricher_name='local.stats-keywords',enricher_config={'top_k':0})
    assert client.post('/api/admin/intake/stage',json=body).status_code==422
    assert client.put('/api/admin/processors',json={'urls':['https://user:secret@processor.test']}).status_code==422
    assert not app.state.store.list_artifacts(doc['file_id'])


def test_remote_processor_receives_only_scoped_revoked_model_grant(app,monkeypatch):
    store=app.state.store;doc=document(store,app.state.settings.source_root)
    store.save_configuration({'chat_model':'selected-chat'})
    store.save_processor_urls(['http://processor.test'])
    descriptor=ProcessorDescriptor(name='toolbox.test',version='1',display_name='Test model enrichment',description='Test',kind=ProcessorKind.ENRICHER,
        capabilities=Capability(scope_types=['object']),model_requirements={'chat':'required'})
    captured=[]
    statuses=[]
    class Remote:
        def __init__(self,*args,**kwargs): pass
        def descriptor(self): return descriptor
        def enrich(self,request):
            context=request.model_context;captured.append(context)
            assert context.token!='secret-not-for-clients'
            assert context.bindings=={'chat':'selected-chat'}
            with TestClient(app) as gateway:
                statuses.append(gateway.get('/api/processor-model/v1/models').status_code)
                assert statuses[-1]==401
                headers={'Authorization':'Bearer '+context.token}
                assert gateway.post('/api/processor-model/v1/chat/completions',headers=headers,json={'model':'other','messages':[{'role':'user','content':'test'}]}).status_code==403
                r=gateway.post('/api/processor-model/v1/chat/completions',headers=headers,json={'model':'selected-chat','messages':[{'role':'user','content':'test'}]})
                statuses.append(r.status_code)
                assert r.status_code==200,r.text
            return EnrichmentResponse(request_id=request.request_id,processor=descriptor,artifacts=[Artifact(id='result',kind='test',media_type='application/json',standard_data={'artifact_type':'wiki_markdown','title':'Synthetic wiki','markdown':'Generated','citations':[]})])
    monkeypatch.setattr(processors,'ProcessorClient',Remote)
    jid=create_plan(app,[doc['source_relpath']],enricher_name=descriptor.name)
    start(app,jid);result=execute(app,jid);assert result['status']=='done',(result['logs'],statuses)
    with TestClient(app) as gateway:
        assert gateway.get('/api/processor-model/v1/models',headers={'Authorization':'Bearer '+captured[0].token}).status_code==403
    assert len(store.list_artifacts(doc['file_id']))==1


def test_gateway_budget_expiry_and_job_lease(app):
    store=app.state.store
    store.save_configuration({'chat_model':'selected-chat'})
    jid=store.enqueue('plan',{'items':[]});store.claim('owner')
    selection={'model_requirements':{'chat':'required'}}
    with grant(store,app.state.settings,selection,jid,'owner') as context:
        key=grant_id(context.token)
        for _ in range(16): store.processor_grant(key,capability='chat',model='selected-chat',consume=True)
        with pytest.raises(ValueError,match='budget exhausted'): store.processor_grant(key,capability='chat',model='selected-chat',consume=True)
        row=store.setting(key,{});row['expires_at']=(now()-timedelta(seconds=1)).isoformat();store.save_setting(key,row)
        with pytest.raises(ValueError,match='expired'): store.processor_grant(key)
    with grant(store,app.state.settings,selection,jid,'owner') as context:
        store.control_job(jid,'cancel','unused');store.checkpoint(jid,'owner')
        with pytest.raises(ValueError,match='no longer owns'): store.processor_grant(grant_id(context.token))


def test_response_identity_scope_and_size_validation():
    from osii.processor_sdk import SynthesisRequest,ScopeInput,DocumentInput,SynthesisResponse,ProvenanceRef
    descriptor=processors.MODEL_SYNTHESIS
    request=SynthesisRequest(request_id='expected',scope=ScopeInput(scope_type='object',scope_id='one',documents=[DocumentInput(file_id='one',filename='a',text='abc')]))
    selection={'kind':'synthesizer','descriptor':descriptor.model_dump(mode='json')}
    for response in (SynthesisResponse(request_id='wrong',processor=descriptor,markdown='x'),SynthesisResponse(request_id='expected',processor=descriptor,markdown='x',citations=[ProvenanceRef(file_id='outside')]), SynthesisResponse(request_id='expected',processor=descriptor,markdown='x',citations=[ProvenanceRef(file_id='one',char_end=100)])):
        with pytest.raises(processors.ProcessorError): processors.validate_response(response,request,selection)
