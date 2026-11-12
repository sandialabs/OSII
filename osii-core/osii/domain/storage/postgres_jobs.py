"""Shared operational job adapter over the existing PostgreSQL jobs table."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import json
import uuid

from .job_store import (JobRecord, JobLease, ClaimedJob, JobOwnershipLost,
                        bounded_job_list, validate_checkpoint, validate_submission)

GENERATION = '_osii_claim_generation'


class PostgresJobStore:
    def __init__(self, engine, *, lease_seconds=300):
        if engine.dialect.name != 'postgresql' or lease_seconds <= 0:
            raise ValueError('PostgreSQL and a positive lease duration are required')
        self.engine, self.lease_seconds = engine, lease_seconds

    @staticmethod
    def _sql(conn, query, **values):
        from sqlalchemy import text
        return conn.execute(text(query), values)

    @staticmethod
    def _record(row):
        if row is None:
            return None
        native = deepcopy(dict(row))
        state = {'pausing': 'pause_requested', 'cancelling': 'cancel_requested'}.get(row['status'], row['status'])
        payload = deepcopy(row['payload'])
        return JobRecord(row['id'], row['id'], row['kind'], state, payload, deepcopy(payload), tuple(row['logs']), native)

    def get(self, job_id):
        with self.engine.connect() as conn:
            return self._record(self._sql(conn, 'SELECT * FROM jobs WHERE id=:id', id=job_id).mappings().first())

    def list(self, *, limit=100):
        with self.engine.connect() as conn:
            return tuple(self._record(row) for row in self._sql(conn,
                'SELECT * FROM jobs ORDER BY created_at DESC,id LIMIT :limit', limit=bounded_job_list(limit)).mappings())

    def submit(self, kind, payload):
        validate_submission(kind, payload)
        identity = str(uuid.uuid4())
        with self.engine.begin() as conn:
            self._sql(conn, """INSERT INTO jobs(id,kind,status,payload,logs,attempts,created_at)
                VALUES (:id,:kind,'queued',CAST(:payload AS jsonb),'[]',0,CURRENT_TIMESTAMP)""",
                id=identity, kind=kind, payload=json.dumps(payload, allow_nan=False))
        return self.get(identity)

    def claim(self, worker_id):
        if not worker_id:
            raise ValueError('worker_id is required')
        with self.engine.begin() as conn:
            self._sql(conn, """UPDATE jobs SET status=CASE status WHEN 'pausing' THEN 'paused'
                WHEN 'cancelling' THEN 'cancelled' ELSE 'queued' END,worker_id=NULL,lease_until=NULL
                WHERE status IN ('running','pausing','cancelling') AND lease_until<CURRENT_TIMESTAMP""")
            self._sql(conn, """UPDATE jobs SET status='error',logs='["Worker recovery exhausted after three attempts."]'
                WHERE status='queued' AND attempts>=3""")
            row = self._sql(conn, """SELECT * FROM jobs WHERE status='queued' AND attempts<3
                ORDER BY created_at,id LIMIT 1 FOR UPDATE SKIP LOCKED""").mappings().first()
            if row is None:
                return None
            generation = uuid.uuid4().hex
            payload = {**row['payload'], GENERATION: generation}
            self._sql(conn, """UPDATE jobs SET status='running',worker_id=:worker,attempts=attempts+1,
                lease_until=CURRENT_TIMESTAMP+(:seconds * interval '1 second'),payload=CAST(:payload AS jsonb)
                WHERE id=:id""", worker=worker_id, seconds=self.lease_seconds, payload=json.dumps(payload), id=row['id'])
            current = self._sql(conn, 'SELECT * FROM jobs WHERE id=:id', id=row['id']).mappings().one()
            return ClaimedJob(self._record(current), JobLease(row['id'], worker_id, generation))

    def _owned(self, conn, lease):
        row = self._sql(conn, """SELECT * FROM jobs WHERE id=:id AND worker_id=:worker
            AND status IN ('running','pausing','cancelling') AND lease_until>CURRENT_TIMESTAMP
            AND payload->>:key=:generation FOR UPDATE""", id=lease.job_id, worker=lease.worker_id,
            key=GENERATION, generation=lease.generation).mappings().first()
        if row is None:
            raise JobOwnershipLost('Worker no longer owns this job claim')
        return row

    def heartbeat(self, lease):
        with self.engine.begin() as conn:
            self._owned(conn, lease)
            self._sql(conn, "UPDATE jobs SET lease_until=CURRENT_TIMESTAMP+(:seconds * interval '1 second') WHERE id=:id",
                seconds=self.lease_seconds, id=lease.job_id)

    def checkpoint(self, lease, *, index=None, item=None):
        validate_checkpoint(index, item)
        with self.engine.begin() as conn:
            row = self._owned(conn, lease)
            payload = deepcopy(row['payload'])
            if index is not None:
                if index >= len(payload.get('items', [])):
                    raise ValueError('Checkpoint item is outside this run')
                payload['items'][index] = item
            state = {'pausing':'paused', 'cancelling':'cancelled'}.get(row['status'], 'running')
            self._sql(conn, """UPDATE jobs SET payload=CAST(:payload AS jsonb),status=:status,
                worker_id=CASE WHEN :release THEN NULL ELSE worker_id END,
                lease_until=CASE WHEN :release THEN NULL ELSE lease_until END WHERE id=:id""",
                payload=json.dumps(payload), status=state, release=state != 'running', id=lease.job_id)
        return self.get(lease.job_id)

    def finish(self, lease, *, outcome='done', logs=(), error=None, reschedule=False):
        if outcome not in {'done','error','paused','cancelled'}:
            raise ValueError('Invalid job outcome')
        with self.engine.begin() as conn:
            row = self._owned(conn, lease)
            state = {'pausing':'paused', 'cancelling':'cancelled'}.get(row['status']) or ('error' if error else 'queued' if reschedule else outcome)
            messages = list(logs) if logs else list(row['logs'])
            if error:
                messages.append(error)
            self._sql(conn, """UPDATE jobs SET status=:status,logs=CAST(:logs AS jsonb),worker_id=NULL,lease_until=NULL,
                attempts=CASE WHEN :yielding THEN 0 ELSE attempts END WHERE id=:id""",
                status=state, logs=json.dumps(messages[-2000:]), yielding=reschedule and state=='queued', id=lease.job_id)
        return self.get(lease.job_id)

    def control(self, job_id, action, *, configuration_stamp=''):
        with self.engine.begin() as conn:
            row = self._sql(conn, 'SELECT * FROM jobs WHERE id=:id FOR UPDATE', id=job_id).mappings().first()
            if row is None:
                raise KeyError('Job not found')
            state = row['status']
            transitions = {'pause': {'queued':'paused', 'running':'pausing'}, 'resume': {'paused':'queued'},
                'cancel': {'queued':'cancelled','paused':'cancelled','running':'cancelling','pausing':'cancelling'},
                'retry': {'error':'queued'}}
            target = transitions.get(action, {}).get(state)
            if target is None:
                raise ValueError(f'Cannot {action} a {state} run')
            stamp = configuration_stamp() if callable(configuration_stamp) else configuration_stamp
            payload = deepcopy(row['payload'])
            if target == 'queued' and payload.get('configuration_stamp', stamp) != stamp:
                raise ValueError('Model or processor settings changed; stage a new plan')
            if action == 'retry':
                payload['items'] = [{**item, 'status':'pending', 'error':None,
                    'started_at':None,'finished_at':None,'duration_seconds':None} if item.get('status')=='error' else item
                    for item in payload.get('items', [])]
            self._sql(conn, """UPDATE jobs SET status=:status,payload=CAST(:payload AS jsonb),
                attempts=CASE WHEN :reset THEN 0 ELSE attempts END WHERE id=:id""",
                status=target, payload=json.dumps(payload), reset=target=='queued', id=job_id)
        return self.get(job_id)
