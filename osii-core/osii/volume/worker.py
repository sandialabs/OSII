"""Durable single-host coordinator. Run under nohup or a terminal multiplexer over SSH."""

from __future__ import annotations

import signal
import threading
import time
import uuid

from .processing import process
from .scanner import InterruptedRun, scan
from .store import VolumeStore, database_path


def execute(
    store: VolumeStore,
    run: dict,
    owner: str,
    stopping: threading.Event,
    client_factory=None,
) -> None:
    finished = threading.Event()

    def heartbeat():
        while not finished.wait(5):
            try:
                if not store.heartbeat(run["id"], owner):
                    return
            except Exception:
                return  # Commits independently verify the lease.

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    error = None
    try:
        if run["kind"] == "scan":
            scan(store, run, owner, stopping)
        else:
            process(
                store,
                run,
                owner,
                stopping,
                **({"client_factory": client_factory} if client_factory else {}),
            )
    except InterruptedRun:
        pass
    except Exception as exc:
        error = (
            str(exc)[:500]
            if isinstance(exc, ValueError)
            else f"Run stopped ({type(exc).__name__}); check database, source, and processor availability"
        )
    finally:
        finished.set()
        thread.join(timeout=6)
    with store.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM runs WHERE id=? AND owner=? AND lease_until>?",
            (run["id"], owner, time.time()),
        ).fetchone()
        if not row:
            return
        table = "directories" if run["kind"] == "scan" else "work_items"
        failed = conn.execute(
            f"SELECT count(*) FROM {table} WHERE run_id=? AND status='error'",
            (run["id"],),
        ).fetchone()[0]
        pending = conn.execute(
            f"SELECT count(*) FROM {table} WHERE run_id=? AND status IN ('pending','running')",
            (run["id"],),
        ).fetchone()[0]
        status = row["status"]
        if status == "running":
            status = (
                "error"
                if error
                else "queued"
                if pending
                else "error"
                if failed
                else "done"
            )
        if error:
            conn.execute(
                "INSERT INTO events(run_id,created,message) VALUES(?,?,?)",
                (run["id"], time.time(), error),
            )
        conn.execute(
            f"UPDATE {table} SET status='pending' WHERE run_id=? AND status='running'",
            (run["id"],),
        )
        conn.execute(
            "UPDATE runs SET status=?,failed=?,error=?,owner=NULL,lease_until=NULL,updated=? WHERE id=?",
            (status, failed, error, time.time(), run["id"]),
        )


def main() -> None:
    store = VolumeStore(database_path())
    store.initialize()
    stopping = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stopping.set())
    owner = uuid.uuid4().hex
    while not stopping.is_set():
        run = store.claim(owner)
        if run:
            execute(store, run, owner, stopping)
        else:
            stopping.wait(1)


if __name__ == "__main__":
    main()
