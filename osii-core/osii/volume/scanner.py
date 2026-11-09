"""Streaming discovery; directory completion is the deletion boundary."""

from __future__ import annotations

import os
import fnmatch
import json
import multiprocessing
import queue
from contextlib import contextmanager
from pathlib import Path
import stat
import time
import uuid

from .store import VolumeStore

BATCH_SIZE = 500


class InterruptedRun(Exception):
    """Control changed or coordinator lease was lost; replay unfinished work."""


def check_owner(store: VolumeStore, conn, run_id: int, owner: str) -> None:
    if not store.owned(conn, run_id, owner):
        raise InterruptedRun()


def checked_path(root: Path, relative: str) -> Path:
    """Reject links in any component and traversal outside the registered root."""
    path = root
    parts = Path(relative).parts
    if Path(relative).is_absolute() or any(part in {"..", "."} for part in parts):
        raise ValueError("Invalid source path")
    for part in parts:
        path /= part
        if path.is_symlink():
            raise ValueError("Symbolic links are not followed")
    if path.resolve() != path or not path.is_relative_to(root) or root.is_symlink():
        raise ValueError("Source path changed or escaped its root")
    return path


@contextmanager
def open_directory(root: Path, relative: str):
    path = checked_path(root, relative)
    if os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW"):
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        fd = os.open(root, flags)
        try:
            for part in Path(relative).parts:
                child = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = child
            yield fd, os.fstat(fd)
        finally:
            os.close(fd)
    else:
        yield path, path.stat()


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


def _directory_batches(source: dict, relative: str, options: dict, stopping):
    root = Path(source["root"])
    token = uuid.uuid4().hex
    rows, directories = [], []
    partial = False
    try:
        root_info = root.stat()
        if (str(root_info.st_dev), str(root_info.st_ino)) != (
            source["device"],
            source["inode"],
        ):
            raise ValueError(
                "Source root identity changed; verify the reconnected source"
            )
        with (
            open_directory(root, relative) as (target, before),
            os.scandir(target) as children,
        ):
            for child in children:
                if stopping.is_set():
                    raise InterruptedRun()
                path = f"{relative}/{child.name}" if relative else child.name
                excluded = (
                    not options.get("show_hidden", True) and child.name.startswith(".")
                ) or any(
                    fnmatch.fnmatchcase(path.lower(), pattern.lower())
                    for pattern in options.get("exclude_patterns", [])
                )
                kind, state, error, status = "unknown", "known", None, "present"
                size, mtime, ctime, device, inode = 0, 0, 0, None, None
                if excluded:
                    state, status = "skipped", "excluded"
                else:
                    try:
                        info = child.stat(follow_symlinks=False)
                        kind = (
                            "file"
                            if stat.S_ISREG(info.st_mode)
                            else "directory"
                            if stat.S_ISDIR(info.st_mode)
                            else "symlink"
                            if stat.S_ISLNK(info.st_mode)
                            else "special"
                        )
                        size, mtime, ctime = (
                            info.st_size if kind == "file" else 0,
                            info.st_mtime_ns,
                            info.st_ctime_ns,
                        )
                        device, inode = str(info.st_dev), str(info.st_ino)
                        if kind == "directory":
                            depth = len(Path(path).parts)
                            if (
                                options.get("max_depth") is None
                                or depth <= options["max_depth"]
                            ) and (
                                options.get("cross_filesystems")
                                or device == source["device"]
                            ):
                                directories.append(path)
                            else:
                                status, state = "excluded", "skipped"
                        elif (
                            kind == "file"
                            and options.get("include_patterns")
                            and not any(
                                fnmatch.fnmatchcase(path.lower(), p.lower())
                                for p in options["include_patterns"]
                            )
                        ):
                            status, state = "excluded", "skipped"
                    except OSError as exc:
                        state, partial = "unavailable", True
                        error = f"Metadata unavailable ({type(exc).__name__}); retry this directory"
                rows.append(
                    (
                        source["id"],
                        path,
                        relative,
                        child.name,
                        kind,
                        Path(child.name).suffix.lower(),
                        size,
                        mtime,
                        ctime,
                        device,
                        inode,
                        time.time(),
                        token,
                        state,
                        error,
                        status,
                    )
                )
                if len(rows) >= BATCH_SIZE:
                    yield "batch", rows, directories
                    rows, directories = [], []
        if rows:
            yield "batch", rows, directories
            rows, directories = [], []
        after = checked_path(root, relative).stat()
        if (before.st_dev, before.st_ino, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_mtime_ns,
        ):
            raise ValueError(
                "Directory changed during enumeration; retry to establish coverage"
            )
        yield "complete", token, partial
    except (OSError, ValueError) as exc:
        # Flush readable siblings even when enumeration itself fails midway.
        if rows:
            yield "batch", rows, directories
        reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        yield "error", f"Directory unavailable ({reason}); coverage incomplete", None


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


def _reader(source, relative, options, output):
    import threading

    try:
        for message in _directory_batches(source, relative, options, threading.Event()):
            output.put(message)
    except Exception as exc:
        output.put(("error", f"Directory reader failed ({type(exc).__name__})", None))


def _stop_reader(process, channel):
    if process.is_alive():
        process.terminate()
    process.join(timeout=0.5)
    if process.is_alive():
        process.kill()
        process.join(timeout=0.5)
    channel.close()
    channel.cancel_join_thread()
    return not process.is_alive()


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
