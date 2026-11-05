"""Streaming discovery; directory completion is the deletion boundary."""

from __future__ import annotations

import os
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
    with store.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        check_owner(store, conn, run["id"], owner)
        changed = "entries.size_bytes!=excluded.size_bytes OR entries.mtime_ns!=excluded.mtime_ns OR entries.ctime_ns!=excluded.ctime_ns OR entries.kind!=excluded.kind OR entries.status!='present'"
        conn.executemany(
            f"""INSERT INTO entries(
          source_id,path,parent,name,kind,suffix,size_bytes,mtime_ns,ctime_ns,device,inode,observed,seen_token)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source_id,path) DO UPDATE SET
          revision=entries.revision+CASE WHEN {changed} THEN 1 ELSE 0 END,
          extraction_id=CASE WHEN {changed} THEN NULL ELSE entries.extraction_id END,
          kind=excluded.kind,suffix=excluded.suffix,size_bytes=excluded.size_bytes,
          mtime_ns=excluded.mtime_ns,ctime_ns=excluded.ctime_ns,device=excluded.device,
          inode=excluded.inode,status='present',observed=excluded.observed,seen_token=excluded.seen_token""",
            rows,
        )
        conn.executemany(
            "INSERT INTO directories(run_id,path) VALUES(?,?) ON CONFLICT DO NOTHING",
            ((run["id"], p) for p in directories),
        )
        conn.execute("UPDATE runs SET updated=? WHERE id=?", (time.time(), run["id"]))


def scan(store: VolumeStore, run: dict, owner: str, stopping) -> None:
    source = store.source(run["source_id"])
    root = Path(source["root"])
    while True:
        if stopping.is_set():
            raise InterruptedRun()
        with store.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            check_owner(store, conn, run["id"], owner)
            directory = conn.execute(
                "SELECT path FROM directories WHERE run_id=? AND status='pending' ORDER BY path LIMIT 1",
                (run["id"],),
            ).fetchone()
            if directory is None:
                return
            relative = directory["path"]
            conn.execute(
                "UPDATE directories SET status='running' WHERE run_id=? AND path=?",
                (run["id"], relative),
            )
        token = (
            uuid.uuid4().hex
        )  # New attempt, including replay of a very large directory.
        rows, directories = [], []
        try:
            root_info = root.stat()
            if (str(root_info.st_dev), str(root_info.st_ino)) != (
                source["device"],
                source["inode"],
            ):
                raise ValueError("Source root identity changed")
            with (
                open_directory(root, relative) as (target, before),
                os.scandir(target) as children,
            ):
                for child in children:
                    if stopping.is_set():
                        raise InterruptedRun()
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
                    path = f"{relative}/{child.name}" if relative else child.name
                    rows.append(
                        (
                            run["source_id"],
                            path,
                            relative,
                            child.name,
                            kind,
                            Path(child.name).suffix.lower(),
                            info.st_size if kind == "file" else 0,
                            info.st_mtime_ns,
                            info.st_ctime_ns,
                            str(info.st_dev),
                            str(info.st_ino),
                            time.time(),
                            token,
                        )
                    )
                    if kind == "directory":
                        directories.append(path)
                    if len(rows) >= BATCH_SIZE:
                        _write_batch(store, run, owner, rows, directories)
                        rows, directories = [], []
            _write_batch(store, run, owner, rows, directories)
            # Re-check the directory after enumeration; a changed mount or link
            # must not turn a partial enumeration into an authoritative absence.
            after = checked_path(root, relative).stat()
            if (before.st_dev, before.st_ino, before.st_mtime_ns) != (
                after.st_dev,
                after.st_ino,
                after.st_mtime_ns,
            ):
                raise ValueError(
                    "Directory changed during enumeration; retry to establish coverage"
                )
            with store.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                check_owner(store, conn, run["id"], owner)
                conn.execute(
                    """WITH RECURSIVE missing(id,path) AS (
                  SELECT id,path FROM entries WHERE source_id=? AND parent=? AND seen_token!=?
                  UNION SELECT child.id,child.path FROM entries child JOIN entries parent
                  ON child.source_id=parent.source_id AND child.parent=parent.path
                  WHERE parent.source_id=? AND parent.parent=? AND parent.kind!='directory'
                  UNION ALL SELECT e.id,e.path FROM entries e JOIN missing m ON e.parent=m.path
                  WHERE e.source_id=?) UPDATE entries SET status='missing',
                  revision=revision+CASE WHEN status!='missing' THEN 1 ELSE 0 END,
                  extraction_id=NULL WHERE id IN (SELECT id FROM missing)""",
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
                    "UPDATE directories SET status='done',error=NULL WHERE run_id=? AND path=?",
                    (run["id"], relative),
                )
                conn.execute(
                    "UPDATE runs SET completed=completed+1,updated=? WHERE id=?",
                    (time.time(), run["id"]),
                )
        except (OSError, ValueError) as exc:
            # Preserve successful batches, but never infer absence in this directory.
            with store.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                check_owner(store, conn, run["id"], owner)
                reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
                message = f"Directory unavailable ({reason}); coverage incomplete"
                conn.execute(
                    "UPDATE directories SET status='error',error=? WHERE run_id=? AND path=?",
                    (message, run["id"], relative),
                )
                conn.execute(
                    "INSERT INTO events(run_id,created,path,message) VALUES(?,?,?,?)",
                    (run["id"], time.time(), relative, message),
                )
