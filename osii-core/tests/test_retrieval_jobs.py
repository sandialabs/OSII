"""Shared bounded contracts on temporary sidecars and real isolated PostgreSQL.

Retrieval ranks are deliberately fixture-controlled: native ranking is covered
by the existing local and hosted search suites, not assumed identical here.
"""
from dataclasses import replace
import json

import pytest

from test_library_reads import reader, postgres_reader, TEXT, ORIGIN
from osii.domain.read.contracts import ReadScope
from osii.domain.storage.retrieval import RetrievalRequest, BoundedRetriever
from osii.domain.storage.job_store import JobOwnershipLost, JobLease


@pytest.fixture(params=['sidecar','postgres'])
def queue(request, tmp_path):
    if request.param == 'sidecar':
        module = pytest.importorskip('osii.domain.storage.sidecar_jobs')
        return module.SidecarJobStore(tmp_path / '.osii')
    from sqlalchemy import text
    from osii.domain.storage.postgres_jobs import PostgresJobStore
    engine = request.getfixturevalue('postgres_reader').engine
    with engine.begin() as conn:
        conn.execute(text('''CREATE TABLE jobs(id text PRIMARY KEY,status text,kind text,payload jsonb,
            logs jsonb,attempts integer,worker_id text,lease_until timestamptz,created_at timestamptz)'''))
    return PostgresJobStore(engine)


def submit(queue):
    return queue.submit('test', {'items':[{'status':'pending'}, {'status':'done','result':'retained'}]})


def expire(queue, lease):
    if hasattr(queue, 'root'):
        with queue._connection(write=True) as conn:
            conn.execute("UPDATE queue_jobs SET heartbeat_at='2000-01-01T00:00:00+00:00' WHERE id=?", (lease.job_id,))
    else:
        from sqlalchemy import text
        with queue.engine.begin() as conn:
            conn.execute(text("UPDATE jobs SET lease_until=now()-interval '1 second' WHERE id=:id"), {'id':lease.job_id})


def test_job_claim_checkpoint_heartbeat_finish_and_list(queue):
    assert queue.claim('worker') is None
    record = submit(queue)
    claimed = queue.claim('worker')
    assert claimed.job.job_id == record.job_id and claimed.job.state == 'running'
    assert queue.claim('another-worker') is None
    queue.heartbeat(claimed.lease)
    saved = queue.checkpoint(claimed.lease, index=0, item={'status':'done','result':'saved'})
    assert saved.progress['items'][0]['result'] == 'saved'
    finished = queue.finish(claimed.lease)
    assert finished.state == 'done' and finished.progress['items'][1]['result'] == 'retained'
    assert queue.list(limit=1)[0].job_id == record.job_id
    with pytest.raises(JobOwnershipLost):
        queue.finish(claimed.lease)
    with pytest.raises(ValueError):
        queue.list(limit=1000)
    with pytest.raises(ValueError):
        queue.submit('test', {'invalid':float('nan')})
    assert len(queue.list()) == 1


@pytest.mark.parametrize('action,target', [('pause','paused'), ('cancel','cancelled')])
def test_job_controls_are_cooperative_and_checkpointed(queue, action, target):
    record = submit(queue)
    claimed = queue.claim('worker')
    controlled = queue.control(record.job_id, action)
    assert controlled.state == ('pause_requested' if action == 'pause' else 'cancel_requested')
    saved = queue.checkpoint(claimed.lease, index=0, item={'status':'done','result':'kept'})
    assert saved.state == target
    assert saved.progress['items'][0]['result'] == 'kept'
    with pytest.raises(JobOwnershipLost):
        queue.heartbeat(claimed.lease)
    if target == 'paused':
        queue.control(record.job_id, 'resume')
        newer = queue.claim('worker')
        assert newer.job.progress['items'][0]['result'] == 'kept'
        assert newer.lease.generation != claimed.lease.generation
    else:
        with pytest.raises(ValueError):
            queue.control(record.job_id, 'resume')


def test_job_failed_checkpoint_is_atomic_and_retry_keeps_completed_work(queue):
    record = submit(queue)
    claimed = queue.claim('worker')
    with pytest.raises(ValueError):
        queue.checkpoint(claimed.lease, index=99, item={'status':'done'})
    assert queue.get(record.job_id).progress['items'][0]['status'] == 'pending'
    queue.finish(claimed.lease, error='temporary failure')
    assert queue.get(record.job_id).state == 'error'
    assert any('temporary failure' in line for line in queue.get(record.job_id).logs)
    queue.control(record.job_id, 'retry')
    newer = queue.claim('worker')
    assert newer.job.progress['items'][1]['result'] == 'retained'
    for mutation in (queue.heartbeat, queue.checkpoint, queue.finish):
        with pytest.raises(JobOwnershipLost):
            mutation(claimed.lease)
    assert queue.get(record.job_id).state == 'running'


def test_job_expired_claim_is_recoverable_but_cannot_be_resurrected(queue):
    record = submit(queue)
    claimed = queue.claim('same-worker')
    expire(queue, claimed.lease)
    with pytest.raises(JobOwnershipLost):
        queue.heartbeat(claimed.lease)
    newer = queue.claim('same-worker')
    assert newer.job.job_id == record.job_id and newer.lease.generation != claimed.lease.generation
    with pytest.raises(JobOwnershipLost):
        queue.finish(claimed.lease, error='late failure')
    queue.finish(newer.lease)
    assert queue.get(record.job_id).state == 'done'


def test_wrong_owner_and_unknown_job_cannot_mutate_state(queue):
    record = submit(queue)
    claimed = queue.claim('worker')
    with pytest.raises(JobOwnershipLost):
        queue.checkpoint(replace(claimed.lease, worker_id='wrong'))
    with pytest.raises(JobOwnershipLost):
        queue.finish(JobLease('unknown','worker','unknown'))
    assert queue.get('unknown') is None
    with pytest.raises(KeyError):
        queue.control('unknown','pause')
    assert queue.get(record.job_id).state == 'running'


def test_rescheduling_batches_does_not_consume_worker_recovery_attempts(queue):
    record = submit(queue)
    for number in range(5):
        claimed = queue.claim('batch-worker')
        assert claimed is not None and claimed.job.job_id == record.job_id
        queue.checkpoint(claimed.lease, index=0, item={'status':'done', 'batch':number})
        queue.finish(claimed.lease, reschedule=True)
    last = queue.claim('batch-worker')
    assert last.job.progress['items'][0]['batch'] == 4
    queue.finish(last.lease)


def test_sidecar_explicit_stores_do_not_change_each_others_default(tmp_path):
    module = pytest.importorskip('osii.domain.storage.sidecar_jobs')
    from osii.domain.processing import jobs
    jobs.configure_job_store(tmp_path / 'default')
    default = jobs._STATE_DB
    first, second = module.SidecarJobStore(tmp_path / 'first'), module.SidecarJobStore(tmp_path / 'second')
    record = submit(first)
    assert second.get(record.job_id) is None
    second.submit('second', {})
    assert len(first.list()) == 1 and len(second.list()) == 1
    assert jobs._STATE_DB == default


@pytest.mark.parametrize('failed', [False, True])
def test_local_worker_uses_shared_claim_completion(tmp_path, monkeypatch, failed):
    module = pytest.importorskip('osii.domain.storage.sidecar_jobs')
    from osii import worker
    from osii.domain.processing import jobs
    root = tmp_path / '.osii'
    queue = module.SidecarJobStore(root)
    queued = submit(queue)
    monkeypatch.setenv('OSII_ROOT', str(root))
    def execute(job):
        if failed:
            raise ValueError('Test worker failure')
        run = jobs.get_run(job['run_id'])
        run['status'] = 'done'
        jobs.save_run(run)
    monkeypatch.setattr(worker, 'execute_job', execute)
    def stop(_):
        raise KeyboardInterrupt()
    monkeypatch.setattr(worker.time, 'sleep', stop)
    with pytest.raises(KeyboardInterrupt):
        worker.main()
    assert queue.get(queued.job_id).state == ('error' if failed else 'done')


@pytest.mark.parametrize('scope', [ReadScope(), ReadScope('object','sha256-a'),
    ReadScope('folder','reports'), ReadScope('collection','col-test')])
def test_retrieval_preserves_source_evidence_and_metadata_on_both_stores(reader, scope):
    def native(request):
        rows = []
        for doc in reader.list_documents(request.scope).items:
            text = reader.get_representation(doc.file_id)
            rows.append({'file_id':doc.file_id,'chunk_id':'chunk-' + doc.file_id,
                'source_relpath':doc.source_relpath,'representation':text.representation_id,
                'text':text.text,'snippet':text.text[:20],'char_start':0,'char_end':len(text.text),
                'source_origin':ORIGIN,'score':1.,'embedding':[1.,0.]})
        return {'results':rows,'retrieval_mode_used':'lexical','channels_used':['fixture-lexical'], 'corpus_revision':'test-generation'}
    result = BoundedRetriever(native).retrieve(RetrievalRequest('neutron', scope, mode='lexical', top_k=2))
    assert len(result.hits) <= 2 and result.actual_mode == 'lexical'
    assert result.corpus_revision == 'test-generation'
    for hit in result.hits:
        assert hit.text == TEXT and hit.char_end == len(TEXT)
        assert hit.source_origin == ORIGIN and hit.representation
        assert 'embedding' not in hit.native
        assert hit.file_id in {doc.file_id for doc in reader.list_documents(scope).items}
    exported = result.legacy_rows()
    if exported:
        exported[0]['source_origin']['page'] = 999
        assert result.hits[0].source_origin['page'] == 1


def test_retrieval_limits_and_invalid_native_results():
    row = {'file_id':'doc','text':'full text','snippet':'display','char_start':3,'char_end':12,'score':.1}
    retrieve = BoundedRetriever(lambda request: {'results':[row,row], 'retrieval_mode_used':'lexical'})
    result = retrieve.retrieve(RetrievalRequest('query', top_k=1))
    assert result.limited and len(result.hits) == 1
    assert result.hits[0].char_start == 3
    assert retrieve.retrieve(RetrievalRequest('query', max_text_chars=1)).limited
    assert not retrieve.retrieve(RetrievalRequest('query', max_text_chars=1)).hits
    for changes in ({'top_k':0}, {'top_k':True}, {'mode':'unknown'}, {'max_text_chars':0}, {'query':' '}):
        with pytest.raises(ValueError):
            RetrievalRequest(**({'query':'query'} | changes))
    for changes in ({'char_end':1}, {'char_start':None}, {'score':float('nan')}, {'file_id':''}):
        with pytest.raises(ValueError):
            BoundedRetriever(lambda request: {'results':[row | changes]}).retrieve(RetrievalRequest('query'))
    with pytest.raises(ValueError):
        retrieve.retrieve(RetrievalRequest('query', scope=ReadScope('object','other')))
