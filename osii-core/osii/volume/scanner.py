"""Streaming discovery; directory completion is the deletion boundary."""

from __future__ import annotations

import json
import multiprocessing
import queue
from pathlib import Path
import time

from .store import VolumeStore
from osii.domain.processing.directory_scan import (
    InterruptedRun,
    checked_path,
    directory_batches,
    reader as _reader,
    stop_reader as _stop_reader,
)


def _directory_batches(source, relative, options, stopping):
    # Retain the local batch tuning/testing boundary while sharing enumeration.
    yield from directory_batches(
        source, relative, options, stopping, batch_size=BATCH_SIZE
    )


BATCH_SIZE = 500


def check_owner(store: VolumeStore, conn, run_id: int, owner: str) -> None:
    if not store.owned(conn, run_id, owner):
        raise InterruptedRun()


def _write_batch(
    store: VolumeStore, run: dict, owner: str, rows: list[tuple], directories: list[str]
) -> None:
    rows = list({row[1]: row for row in rows}.values())
    with store.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        check_owner(store, conn, run["id"], owner)
        previous = {}
        if rows:
            placeholders = ",".join("?" for _ in rows)
            previous = {
                r["path"]: dict(r)
                for r in conn.execute(
                    f"SELECT path,scan_run_id,size_bytes,metadata_state,kind,status FROM entries WHERE source_id=? AND path IN ({placeholders})",
                    [run["source_id"], *[row[1] for row in rows]],
                )
            }
        changed = "entries.size_bytes!=excluded.size_bytes OR entries.mtime_ns!=excluded.mtime_ns OR entries.ctime_ns!=excluded.ctime_ns OR entries.kind!=excluded.kind OR entries.status!=excluded.status OR entries.metadata_state!=excluded.metadata_state OR entries.device IS NOT excluded.device OR entries.inode IS NOT excluded.inode"
        conn.executemany(
            f"""INSERT INTO entries(
          source_id,path,parent,name,kind,suffix,size_bytes,mtime_ns,ctime_ns,device,inode,observed,seen_token,
          metadata_state,metadata_error,status,scan_run_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(source_id,path) DO UPDATE SET
          revision=entries.revision+CASE WHEN {changed} THEN 1 ELSE 0 END,
          extraction_id=CASE WHEN {changed} THEN NULL ELSE entries.extraction_id END,
          kind=excluded.kind,suffix=excluded.suffix,size_bytes=excluded.size_bytes,
          mtime_ns=excluded.mtime_ns,ctime_ns=excluded.ctime_ns,device=excluded.device,inode=excluded.inode,
          status=excluded.status,observed=excluded.observed,seen_token=excluded.seen_token,
          metadata_state=excluded.metadata_state,metadata_error=excluded.metadata_error,scan_run_id=excluded.scan_run_id""",
            [(*row, run["id"]) for row in rows],
        )
        conn.executemany(
            "INSERT INTO directories(run_id,path) VALUES(?,?) ON CONFLICT DO NOTHING",
            ((run["id"], p) for p in directories),
        )
        checked, byte_delta = 0, 0
        for row in rows:
            old = previous.get(row[1])
            old_current = old and old["scan_run_id"] == run["id"]
            checked += not old_current
            current_size = (
                row[6]
                if row[4] == "file" and row[13] == "known" and row[15] == "present"
                else 0
            )
            old_size = (
                old["size_bytes"]
                if old_current
                and old["kind"] == "file"
                and old["metadata_state"] == "known"
                and old["status"] == "present"
                else 0
            )
            byte_delta += current_size - old_size
            if row[14]:
                conn.execute(
                    "INSERT INTO events(run_id,created,path,message) VALUES(?,?,?,?)",
                    (run["id"], time.time(), row[1], row[14]),
                )
        conn.execute(
            "UPDATE runs SET updated=?,observed_entries=observed_entries+?,known_bytes=known_bytes+?,metadata_errors=metadata_errors+? WHERE id=?",
            (
                time.time(),
                checked,
                byte_delta,
                sum(bool(row[14]) for row in rows),
                run["id"],
            ),
        )


def _finish_directory(store, run, owner, relative, message):
    with store.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        check_owner(store, conn, run["id"], owner)
        error = (
            message[1]
            if message[0] == "error"
            else "Some entry metadata is unavailable; coverage incomplete"
            if message[2]
            else None
        )
        if not error:
            token = message[1]
            conn.execute(
                """WITH RECURSIVE missing(id,path) AS (
              SELECT id,path FROM entries WHERE source_id=? AND parent=? AND seen_token!=? AND status!='excluded'
              UNION SELECT child.id,child.path FROM entries child JOIN entries parent
                ON child.source_id=parent.source_id AND child.parent=parent.path
                WHERE parent.source_id=? AND parent.parent=? AND parent.kind!='directory' AND parent.metadata_state='known'
              UNION ALL SELECT e.id,e.path FROM entries e JOIN missing m ON e.parent=m.path WHERE e.source_id=?)
              UPDATE entries SET status='missing',revision=revision+CASE WHEN status!='missing' THEN 1 ELSE 0 END,extraction_id=NULL
              WHERE id IN (SELECT id FROM missing)""",
                (
                    run["source_id"],
                    relative,
                    token,
                    run["source_id"],
                    relative,
                    run["source_id"],
                ),
            )
        conn.execute(
            "UPDATE directories SET status=?,error=?,updated=? WHERE run_id=? AND path=?",
            ("error" if error else "done", error, time.time(), run["id"], relative),
        )
        conn.execute(
            "UPDATE runs SET completed=completed+1,updated=? WHERE id=?",
            (time.time(), run["id"]),
        )
        if error:
            conn.execute(
                "INSERT INTO events(run_id,created,path,message) VALUES(?,?,?,?)",
                (run["id"], time.time(), relative, error),
            )


def _claim_directory(store, run, owner):
    with store.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        check_owner(store, conn, run["id"], owner)
        row = conn.execute(
            "SELECT path FROM directories WHERE run_id=? AND status='pending' AND attempts<3 ORDER BY path LIMIT 1",
            (run["id"],),
        ).fetchone()
        if row is None:
            conn.execute(
                "UPDATE directories SET status='error',error='Directory recovery exhausted; explicitly resume to retry' WHERE run_id=? AND status='pending' AND attempts>=3",
                (run["id"],),
            )
            return None
        conn.execute(
            "UPDATE directories SET status='running',attempts=attempts+1,updated=? WHERE run_id=? AND path=?",
            (time.time(), run["id"], row["path"]),
        )
        return row["path"]


def scan(store: VolumeStore, run: dict, owner: str, stopping) -> None:
    source = store.source(run["source_id"])
    options = json.loads(run["payload"] or "{}")
    if options.get("source_generation", 1) != source["generation"]:
        raise ValueError(
            "Source generation changed; start a fresh scan after rebinding"
        )
    if not options.get("isolate", False):
        while True:
            if stopping.is_set():
                raise InterruptedRun()
            relative = _claim_directory(store, run, owner)
            if relative is None:
                return
            for message in _directory_batches(source, relative, options, stopping):
                if message[0] == "batch":
                    _write_batch(store, run, owner, message[1], message[2])
                else:
                    _finish_directory(store, run, owner, relative, message)
        return
    context = multiprocessing.get_context("spawn")
    active = {}
    timeouts = 0
    try:
        while True:
            if stopping.is_set():
                raise InterruptedRun()
            with store.connect() as conn:
                check_owner(store, conn, run["id"], owner)
            while len(active) < options.get("readers", 2):
                relative = _claim_directory(store, run, owner)
                if relative is None:
                    break
                output = context.Queue(maxsize=2)
                process = context.Process(
                    target=_reader,
                    args=(source, relative, options, output),
                    daemon=True,
                )
                process.start()
                active[relative] = [process, output, time.monotonic()]
            if not active:
                return
            progress = False
            for relative, task in list(active.items()):
                process, output, last = task
                try:
                    message = output.get(timeout=0.05)
                except queue.Empty:
                    if time.monotonic() - last > options.get("timeout_seconds", 30):
                        message = (
                            "error",
                            "Directory reader timed out; reconnect the share and resume",
                            None,
                        )
                        timeouts += 1
                    elif not process.is_alive():
                        message = (
                            "error",
                            "Directory reader exited before completion; resume to retry",
                            None,
                        )
                    else:
                        continue
                progress = True
                task[2] = time.monotonic()
                if message[0] == "batch":
                    _write_batch(store, run, owner, message[1], message[2])
                else:
                    _finish_directory(store, run, owner, relative, message)
                    reaped = _stop_reader(process, output)
                    del active[relative]
                    if not reaped:
                        raise ValueError(
                            "A filesystem reader remains blocked in the OS; restore the mount before resuming"
                        )
                if timeouts >= options.get("readers", 2):
                    raise ValueError(
                        "Source circuit breaker opened after repeated stalled readers; reconnect and resume"
                    )
            if not progress:
                stopping.wait(0.05)
    finally:
        for process, channel, _ in active.values():
            _stop_reader(process, channel)
