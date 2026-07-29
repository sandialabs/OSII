from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .pathing import display_rel

RUNS: dict[str, dict] = {}
RUNS_LOCK = threading.Lock()
_STATE_DB: Path | None = None


def configure_job_store(osii_root: Path) -> Path:
    """Configure the durable operational-state store for this process."""
    global _STATE_DB
    state_dir = osii_root.resolve() / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    _STATE_DB = state_dir / "jobs.sqlite3"
    with _connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                data_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS queue_jobs (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                error TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_queue_jobs_status_created
              ON queue_jobs(status, created_at);
            """
        )
    return _STATE_DB


def _connection() -> sqlite3.Connection:
    if _STATE_DB is None:
        raise RuntimeError("Job store is not configured. Call configure_job_store first.")
    conn = sqlite3.connect(_STATE_DB, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _now() -> str:
    return datetime.now(UTC).isoformat()


def save_run(run: dict) -> None:
    if _STATE_DB is None:
        return
    with _connection() as conn:
        conn.execute(
            """
            INSERT INTO runs(id, data_json, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET data_json=excluded.data_json, updated_at=excluded.updated_at
            """,
            (run["id"], json.dumps(run), _now()),
        )


def append_log(run_id: str, message: str) -> None:
    with RUNS_LOCK:
        run = RUNS.get(run_id)
        if run is None:
            run = _load_run(run_id)
            if run is None:
                return
            RUNS[run_id] = run
        timestamp = datetime.now().strftime("%H:%M:%S")
        run["logs"].append(f"[{timestamp}] {message}")
        save_run(run)


def create_run_record(
    files: list[Path],
    shared_root: Path,
    upload_root: Path,
    *,
    osii_root: Path | None = None,
) -> dict:
    if osii_root is not None:
        configure_job_store(osii_root)

    run_id = uuid.uuid4().hex
    items = [
        {
            "path": str(p),
            "display": display_rel(p, shared_root, upload_root),
            "status": "pending",
            "artifact": None,
            "datacard": None,
            "error": None,
        }
        for p in files
    ]
    run = {
        "id": run_id,
        "status": "pending",
        "created_at": _now(),
        "started_at": None,
        "finished_at": None,
        "completed": 0,
        "total": len(items),
        "items": items,
        "logs": [],
        "manifest_name": None,
        "manifest_path": None,
        "error": None,
    }
    with RUNS_LOCK:
        RUNS[run_id] = run
        save_run(run)
    return run


def _load_run(run_id: str) -> dict | None:
    if _STATE_DB is None:
        return None
    with _connection() as conn:
        row = conn.execute("SELECT data_json FROM runs WHERE id = ?", (run_id,)).fetchone()
    return json.loads(row["data_json"]) if row else None


def get_run(run_id: str) -> dict | None:
    with RUNS_LOCK:
        run = RUNS.get(run_id)
        if run is not None:
            return run
        run = _load_run(run_id)
        if run is not None:
            RUNS[run_id] = run
        return run


def list_runs(*, limit: int = 100) -> list[dict]:
    if _STATE_DB is None:
        return []
    with _connection() as conn:
        rows = conn.execute(
            "SELECT data_json FROM runs ORDER BY updated_at DESC LIMIT ?", (max(1, min(limit, 500)),)
        ).fetchall()
    return [json.loads(row["data_json"]) for row in rows]


def enqueue_run(run_id: str, payload: dict[str, Any]) -> dict:
    job_id = uuid.uuid4().hex
    now = _now()
    with _connection() as conn:
        conn.execute(
            """INSERT INTO queue_jobs(id, run_id, payload_json, status, created_at)
               VALUES (?, ?, ?, 'queued', ?)""",
            (job_id, run_id, json.dumps(payload), now),
        )
    return {"id": job_id, "run_id": run_id, "status": "queued", "created_at": now}


def claim_next_queue_job() -> dict | None:
    """Claim one queued job atomically; safe when multiple local workers run."""
    with _connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM queue_jobs WHERE status = 'queued' ORDER BY created_at LIMIT 1"
        ).fetchone()
        if row is None:
            conn.commit()
            return None
        started_at = _now()
        conn.execute(
            "UPDATE queue_jobs SET status = 'running', started_at = ? WHERE id = ?",
            (started_at, row["id"]),
        )
        conn.commit()
    return {
        "id": row["id"],
        "run_id": row["run_id"],
        "payload": json.loads(row["payload_json"]),
        "status": "running",
        "created_at": row["created_at"],
        "started_at": started_at,
    }


def complete_queue_job(job_id: str, *, error: str | None = None) -> None:
    with _connection() as conn:
        conn.execute(
            "UPDATE queue_jobs SET status = ?, finished_at = ?, error = ? WHERE id = ?",
            ("error" if error else "done", _now(), error, job_id),
        )


def list_queue_jobs(*, limit: int = 100) -> list[dict]:
    if _STATE_DB is None:
        return []
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM queue_jobs ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 500)),)
        ).fetchall()
    return [
        {
            "id": row["id"],
            "run_id": row["run_id"],
            "status": row["status"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "error": row["error"],
        }
        for row in rows
    ]
