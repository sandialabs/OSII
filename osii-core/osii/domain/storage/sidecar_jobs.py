"""Explicit sidecar operational queue adapter over the existing jobs.sqlite3."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
import json
import uuid

from .job_store import (JobRecord, JobLease, ClaimedJob, JobOwnershipLost,
                        bounded_job_list, validate_checkpoint, validate_submission)


class SidecarJobStore:
    def __init__(self, root: Path, *, lease_seconds: float = 15):
        from osii.domain.processing import jobs
        if lease_seconds <= 0:
            raise ValueError('lease_seconds must be positive')
        self.root, self.lease_seconds = Path(root).resolve(), lease_seconds
        with jobs.using_job_store(self.root):
            jobs.configure_job_store(self.root)

    @contextmanager
    def _connection(self, *, write=False):
        from osii.domain.processing import jobs
        with jobs.using_job_store(self.root):
            conn = jobs._connection()
            try:
                with conn:
                    if write:
                        conn.execute('BEGIN IMMEDIATE')
                    yield conn
            finally:
                conn.close()

    def _record(self, conn, row):
        run = conn.execute('SELECT data_json FROM runs WHERE id=?', (row['run_id'],)).fetchone()
        progress = json.loads(run['data_json']) if run else {}
        payload = json.loads(row['payload_json'])
        native = {**dict(row), 'payload': payload, 'started_at': row['started_at']}
        return JobRecord(row['id'], row['run_id'], payload.get('job_kind', 'intake'), row['status'],
            payload, progress, tuple(progress.get('logs', [])), native)

    def get(self, job_id):
        with self._connection() as conn:
            row = conn.execute('SELECT * FROM queue_jobs WHERE id=?', (job_id,)).fetchone()
            return self._record(conn, row) if row else None

    def list(self, *, limit=100):
        with self._connection() as conn:
            return tuple(self._record(conn, row) for row in conn.execute(
                'SELECT * FROM queue_jobs ORDER BY created_at DESC,id LIMIT ?', (bounded_job_list(limit),)).fetchall())

    def submit(self, kind, payload):
        from osii.domain.processing import jobs
        validate_submission(kind, payload)
        identity = uuid.uuid4().hex
        with jobs.using_job_store(self.root):
            run = jobs.create_run_record([], self.root, self.root, run_id=identity)
            run.update(status='queued', control_state='running', items=payload.get('items', []), total=len(payload.get('items', [])))
            jobs.save_run(run)
            queued = jobs.enqueue_run(identity, {**payload, 'job_kind': kind})
        return self.get(queued['id'])

    def claim(self, worker_id):
        from osii.domain.processing import jobs
        if not worker_id:
            raise ValueError('worker_id is required')
        with jobs.using_job_store(self.root):
            # Keep existing recovery policy, including paused/cancelled requests.
            jobs.recover_stale_queue_jobs(stale_after_seconds=self.lease_seconds)
            jobs.register_worker(worker_id)
            job = jobs.claim_next_queue_job(worker_id)
        if not job:
            return None
        generation = uuid.uuid4().hex
        with self._connection(write=True) as conn:
            row = conn.execute('SELECT * FROM queue_jobs WHERE id=?', (job['id'],)).fetchone()
            if row['worker_id'] != worker_id or row['started_at'] != job['started_at'] or row['status'] != 'running':
                raise JobOwnershipLost('Job was recovered before its claim was returned')
            payload = {**json.loads(row['payload_json']), '_osii_claim_generation': generation}
            conn.execute('UPDATE queue_jobs SET payload_json=? WHERE id=?', (json.dumps(payload), job['id']))
        record = self.get(job['id'])
        return ClaimedJob(record, JobLease(record.job_id, worker_id, generation))

    def _owned(self, conn, lease):
        row = conn.execute('SELECT * FROM queue_jobs WHERE id=?', (lease.job_id,)).fetchone()
        cutoff = datetime.now(UTC) - timedelta(seconds=self.lease_seconds)
        if (row is None or row['worker_id'] != lease.worker_id or
            json.loads(row['payload_json']).get('_osii_claim_generation') != lease.generation or
            row['status'] not in {'running', 'pause_requested', 'cancel_requested'} or
            not row['heartbeat_at'] or datetime.fromisoformat(row['heartbeat_at']) <= cutoff):
            raise JobOwnershipLost('Worker no longer owns this job claim')
        return row

    def heartbeat(self, lease):
        with self._connection(write=True) as conn:
            self._owned(conn, lease)
            now = datetime.now(UTC).isoformat()
            conn.execute('UPDATE queue_jobs SET heartbeat_at=? WHERE id=?', (now, lease.job_id))
            conn.execute('UPDATE workers SET heartbeat_at=? WHERE id=?', (now, lease.worker_id))

    def _write_progress(self, conn, row, progress):
        conn.execute('UPDATE runs SET data_json=?,updated_at=? WHERE id=?',
            (json.dumps(progress), datetime.now(UTC).isoformat(), row['run_id']))

    def checkpoint(self, lease, *, index=None, item=None):
        validate_checkpoint(index, item)
        with self._connection(write=True) as conn:
            row = self._owned(conn, lease)
            progress = self._record(conn, row).progress
            if index is not None:
                if index >= len(progress.get('items', [])):
                    raise ValueError('Checkpoint item is outside this run')
                progress['items'][index] = item
            state = {'pause_requested': 'paused', 'cancel_requested': 'cancelled'}.get(row['status'], 'running')
            progress.update(status=state, control_state=state)
            self._write_progress(conn, row, progress)
            if state != 'running':
                conn.execute('UPDATE queue_jobs SET status=?,worker_id=NULL,heartbeat_at=NULL WHERE id=?', (state, lease.job_id))
        return self.get(lease.job_id)

    def finish(self, lease, *, outcome='done', logs=(), error=None, reschedule=False):
        if outcome not in {'done', 'error', 'paused', 'cancelled'}:
            raise ValueError('Invalid job outcome')
        with self._connection(write=True) as conn:
            row = self._owned(conn, lease)
            progress = self._record(conn, row).progress
            state = {'pause_requested': 'paused', 'cancel_requested': 'cancelled'}.get(row['status'])
            state = state or (progress.get('status') if progress.get('status') in {'paused','cancelled'} else None)
            state = state or ('error' if error else 'queued' if reschedule else outcome)
            now = datetime.now(UTC).isoformat()
            progress.update(status=state, control_state=state, error=error, finished_at=None if state in {'queued','paused'} else now)
            if logs or error:
                messages = list(logs) if logs else list(progress.get('logs', []))
                if error:
                    messages.append(f'Worker error: {error}')
                progress['logs'] = messages[-2000:]
            self._write_progress(conn, row, progress)
            conn.execute('UPDATE queue_jobs SET status=?,error=?,finished_at=?,worker_id=NULL,heartbeat_at=NULL WHERE id=?',
                (state, error, progress['finished_at'], lease.job_id))
        return self.get(lease.job_id)

    def control(self, job_id, action, *, configuration_stamp=''):
        from osii.domain.processing import jobs
        record = self.get(job_id)
        if record is None:
            raise KeyError('Job not found')
        with jobs.using_job_store(self.root):
            jobs.control_run(record.run_id, action)
        return self.get(job_id)
