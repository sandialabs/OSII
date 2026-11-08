import threading
from datetime import timedelta

import pytest
from sqlalchemy import update

from conftest import Provider, document, login
from osii.persistence.postgres import jobs, now
from osii.server.intake import configuration_stamp, plan
from osii.server.worker import process_plan


class NeverExtract:
    def extract(self, request):
        raise AssertionError('Extraction must not be invoked')


def staged(app, paths, *, operation='missing', embed=False):
    store, settings = app.state.store, app.state.settings
    payload = plan(store, settings, paths, operation=operation, embed=embed)
    jid = store.enqueue('plan', payload, status='staged')
    return jid


def execute(app, jid, extractor=NeverExtract(), provider=None):
    store = app.state.store
    job = store.claim('test-worker')
    assert job['id'] == jid
    logs = list(job['logs'])
    def report(entry):
        assert store.progress(jid, 'test-worker', entry)
        logs.append(entry)
    failed = process_plan(store, provider or Provider(), extractor, app.state.settings, job,
                          'test-worker', threading.Event(), report=report)
    store.finish(jid, 'test-worker', logs, failed)
    return store.job(jid)


def test_stage_is_reviewable_not_claimable_and_admin_only(client, app):
    (app.state.settings.source_root/'new.txt').write_text('text')
    for role in ('reader', 'curator'):
        login(client, role)
        assert client.post('/api/admin/intake/stage', json={'paths': ['new.txt']}).status_code == 403
        assert client.get('/api/admin/runs').status_code == 403
    login(client)
    preview = client.post('/api/admin/intake/preview', json={'paths': ['.']})
    assert preview.status_code == 200
    assert [i['path'] for i in preview.json()['items']] == ['new.txt']
    result = client.post('/api/admin/intake/stage', json={'paths': ['new.txt']})
    assert result.status_code == 200 and result.json()['status'] == 'staged'
    assert app.state.store.claim('idle') is None
    assert app.state.store.statistics()['documents'] == 0
    assert 'secret-not-for-clients' not in str(result.json())
    jid=result.json()['id']
    assert client.post(f'/api/admin/runs/{jid}/start', json={}).json()['status'] == 'queued'
    assert client.post(f'/api/admin/runs/{jid}/pause', json={}).json()['status'] == 'paused'
    assert client.post(f'/api/admin/runs/{jid}/resume', json={}).json()['status'] == 'queued'
    assert client.post(f'/api/admin/runs/{jid}/cancel', json={}).json()['status'] == 'cancelled'
    assert client.post(f'/api/admin/runs/{jid}/resume', json={}).status_code == 409


def test_pause_finishes_current_file_resume_skips_completed(app):
    from osii.processor_sdk.models import ExtractionResponse, ProcessorDescriptor, ProcessorKind, TextSegment
    store, settings = app.state.store, app.state.settings
    for name in ('a.txt','b.txt'):
        (settings.source_root/name).write_text(name)
    jid = staged(app, ['.'])
    stamp=configuration_stamp(store,settings)
    store.control_job(jid,'start',stamp)
    class Extractor:
        calls=[]
        def extract(self, request):
            self.calls.append(request.document.filename)
            if request.document.filename == 'a.txt':
                assert store.control_job(jid,'pause',stamp)['status'] == 'pausing'
            return ExtractionResponse(request_id=request.request_id, processor=ProcessorDescriptor(
                name='test',version='1',display_name='Test',description='Test',kind=ProcessorKind.EXTRACTOR),
                segments=[TextSegment(id='p1',text=request.document.filename,source_origin={'page':1})])
    extractor=Extractor()
    assert execute(app,jid,extractor)['status'] == 'paused'
    items=store.job(jid)['payload']['items']
    assert [item['status'] for item in items] == ['done','pending']
    assert store.claim('other') is None
    store.control_job(jid,'resume',stamp)
    assert execute(app,jid,extractor)['status'] == 'done'
    assert extractor.calls == ['a.txt','b.txt']
    assert store.statistics()['documents'] == 2


def test_cancel_at_boundary_and_retry_failed_only(app):
    store,settings=app.state.store,app.state.settings
    document(store,settings.source_root,name='a.txt',content='first text')
    document(store,settings.source_root,name='b.txt',content='second text')
    jid=staged(app,['.'])
    stamp=configuration_stamp(store,settings)
    store.control_job(jid,'start',stamp)
    job=store.claim('owner')
    assert store.control_job(jid,'cancel',stamp)['status']=='cancelling'
    assert store.checkpoint(jid,'owner')=='cancelled'
    store.finish(jid,'owner',[],False)
    assert store.job(jid)['status']=='cancelled'
    jid=staged(app,['.'])
    store.control_job(jid,'start',stamp)
    # A changed source is a file error; the other file is still visited.
    (settings.source_root/'b.txt').write_text('changed after staging')
    result=execute(app,jid)
    assert result['status']=='error'
    assert [item['status'] for item in result['payload']['items']]==['done','error']
    first=result['payload']['items'][0].copy()
    store.control_job(jid,'retry',stamp)
    assert store.job(jid)['payload']['items'][0]==first
    assert store.job(jid)['payload']['items'][1]['status']=='pending'


def test_reembed_preserves_extractions_and_no_partial_vector_replace(app):
    store,settings=app.state.store,app.state.settings
    doc=document(store,settings.source_root)
    old=store.extraction_records(doc['file_id'])
    store.save_configuration({'embedding_model':'new-model'})
    jid=staged(app,[doc['source_relpath']],operation='embed',embed=True)
    store.control_job(jid,'start',configuration_stamp(store,settings))
    result=execute(app,jid)
    assert result['status']=='done'
    assert store.extraction_records(doc['file_id'])==old
    assert store.document_chunks(doc['file_id'])[0]['embedding_model']=='new-model'
    assert store.document(doc['file_id'])['text']==doc['text']
    from osii.model_provider import ProviderError
    class Broken(Provider):
        def embed(self,model,texts):
            raise ProviderError('Provider rate limit reached')
    jid=staged(app,[doc['source_relpath']],operation='embed',embed=True)
    store.control_job(jid,'start',configuration_stamp(store,settings))
    vectors=store.document_chunks(doc['file_id'])
    assert execute(app,jid,provider=Broken())['status']=='error'
    assert store.document_chunks(doc['file_id'])==vectors


def test_expired_pause_cancel_recover_safely_and_old_owner_cannot_finish(app):
    store=app.state.store
    for action,target in [('pause','paused'),('cancel','cancelled')]:
        jid=store.enqueue('plan',{'items':[]})
        store.claim('old')
        store.control_job(jid,action,'unused')
        with store.transaction() as c:
            c.execute(update(jobs).where(jobs.c.id==jid).values(lease_until=now()-timedelta(seconds=1)))
        assert store.claim('new') is None
        assert store.job(jid)['status']==target
        with pytest.raises(ValueError,match='no longer owns'):
            store.checkpoint(jid,'old')
        store.finish(jid,'old',['should not overwrite'],False)
        assert store.job(jid)['status']==target


def test_plan_rejects_escape_symlinks_changed_configuration_and_unindexed_embedding(app):
    store,settings=app.state.store,app.state.settings
    (settings.source_root/'visible.txt').write_text('text')
    (settings.source_root/'link.txt').symlink_to(settings.source_root/'visible.txt')
    for path in ('../outside','/etc/passwd','.hidden','link.txt'):
        with pytest.raises(ValueError):
            plan(store,settings,[path],operation='missing',embed=False)
    store.save_configuration({'embedding_model':'model'})
    with pytest.raises(ValueError,match='Extract text'):
        plan(store,settings,['visible.txt'],operation='embed',embed=True)
    jid=staged(app,['visible.txt'])
    store.save_configuration({'embedding_model':'changed-model'})
    with pytest.raises(ValueError,match='settings changed'):
        store.control_job(jid,'start',configuration_stamp(store,settings))


def test_extraction_history_authenticated_and_preserves_source_regions(client,app):
    doc=document(app.state.store,app.state.settings.source_root)
    assert client.get(f"/api/objects/{doc['file_id']}/extractions").status_code==401
    login(client,'reader')
    history=client.get(f"/api/objects/{doc['file_id']}/extractions").json()['items']
    assert history[0]['primary']
    assert history[0]['response']['segments'][0]['source_origin']['page']==1


def test_active_controls_keep_heartbeat_and_model_changes_blocked(app):
    store=app.state.store
    jid=store.enqueue('plan',{'items':[]})
    store.claim('owner')
    store.control_job(jid,'pause','unused')
    store.heartbeat(jid,'owner')
    assert store.job(jid)['lease_until'] > now()
    with pytest.raises(ValueError,match='Wait for processing'):
        store.save_model_connection('embedding',{'base_url':'http://different.test/v1'})
    with pytest.raises(ValueError,match='Wait for processing'):
        store.save_configuration({'embedding_model':'different'})
    store.checkpoint(jid,'owner')
    store.save_configuration({'embedding_model':'different'})


def test_lost_worker_cannot_replace_document_vectors(app):
    store,settings=app.state.store,app.state.settings
    doc=document(store,settings.source_root)
    rows=store.document_chunks(doc['file_id'])
    jid=store.enqueue('plan',{'items':[]})
    store.claim('owner')
    store.control_job(jid,'cancel','unused')
    store.checkpoint(jid,'owner')
    with pytest.raises(ValueError,match='no longer owns'):
        store.replace_embeddings(doc['file_id'],rows,'wrong-model',job_owner=(jid,'owner'))
    assert store.document_chunks(doc['file_id'])==rows


def test_text_only_refresh_keeps_unchanged_existing_embeddings(app):
    store,settings=app.state.store,app.state.settings
    store.save_configuration({'embedding_model':'existing-model'})
    doc=document(store,settings.source_root)
    before=store.document_chunks(doc['file_id'])
    assert before[0]['embedding'] is not None
    jid=staged(app,[doc['source_relpath']],embed=False)
    store.control_job(jid,'start',configuration_stamp(store,settings))
    assert execute(app,jid)['status']=='done'
    assert store.document_chunks(doc['file_id'])==before
