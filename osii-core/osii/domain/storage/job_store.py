"""Core job contracts; queue/run IDs and ownership are explicit.

This is operational state, not library evidence or inventory. Authorization and
processor/model configuration stay in the owning application composition.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Literal, Protocol


class JobOwnershipLost(ValueError):
    """An expired, released, or superseded claim cannot mutate the current run."""


@dataclass(frozen=True)
class JobRecord:
    job_id: str
    run_id: str
    kind: str
    state: str
    payload: dict
    progress: dict
    logs: tuple[str, ...] = ()
    native: dict = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class JobLease:
    job_id: str
    worker_id: str
    generation: str


@dataclass(frozen=True)
class ClaimedJob:
    job: JobRecord
    lease: JobLease


def bounded_job_list(limit: int) -> int:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Job list limit must be between 1 and 100")
    return limit


def validate_checkpoint(index, item):
    if (index is None) != (item is None):
        raise ValueError("Checkpoint index and item must be supplied together")
    if index is not None and (type(index) is not int or index < 0 or not isinstance(item, dict)):
        raise ValueError("Invalid job checkpoint")
    if item is not None:
        json.dumps(item, allow_nan=False)


def validate_submission(kind, payload):
    if not isinstance(kind, str) or not kind.strip() or not isinstance(payload, dict):
        raise ValueError('A job requires a kind and an explicit JSON payload')
    json.dumps(payload, allow_nan=False)


class JobStore(Protocol):
    def submit(self, kind: str, payload: dict) -> JobRecord: ...
    def get(self, job_id: str) -> JobRecord | None: ...
    def list(self, *, limit: int = 100) -> tuple[JobRecord, ...]: ...
    def claim(self, worker_id: str) -> ClaimedJob | None: ...
    def heartbeat(self, lease: JobLease) -> None: ...
    def checkpoint(self, lease: JobLease, *, index: int | None = None, item: dict | None = None) -> JobRecord: ...
    def finish(self, lease: JobLease, *, outcome: Literal['done', 'error', 'paused', 'cancelled'] = 'done',
               logs: tuple[str, ...] = (), error: str | None = None, reschedule: bool = False) -> JobRecord: ...
    def control(self, job_id: str, action: str, *, configuration_stamp='') -> JobRecord: ...
