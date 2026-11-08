"""Short-lived Processor SDK model grants, scoped to a live leased job."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
import hashlib
import secrets

from osii.persistence.postgres import now
from osii.processor_sdk import ModelContext

PREFIX = 'processor_grant:'


def grant_id(token: str) -> str:
    return PREFIX + hashlib.sha256(token.encode()).hexdigest()


@contextmanager
def grant(store, settings, selection: dict, job_id: str, worker: str):
    requirements = selection.get('model_requirements', {})
    bindings = {kind: store.configuration().get(kind + '_model', '') for kind in requirements}
    bindings = {kind: model for kind, model in bindings.items() if model}
    if not bindings:
        yield None
        return
    store.prune_processor_grants()
    token = secrets.token_urlsafe(32)
    key = grant_id(token)
    store.save_setting(key, {'job_id': job_id, 'worker': worker, 'bindings': bindings,
        'expires_at': (now()+timedelta(minutes=10)).isoformat(), 'remaining_calls': 16})
    try:
        yield ModelContext(gateway_url=settings.processor_gateway_url, token=token, bindings=bindings)
    finally:
        store.delete_setting(key)
