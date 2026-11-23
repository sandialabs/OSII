"""Publish immutable vector snapshots with one atomic pointer, on local disk."""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import uuid

from .atomic import atomic_write_text


@contextmanager
def embedding_writer(osii_root: Path):
    # OS locks are released even after SIGKILL; all providers share the lexical
    # chunk manifest, so serialize writers across the library, not just a model.
    path = osii_root / "embeddings" / ".writer.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            if not handle.read(1):
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError(
                    "Another embedding writer is active; retry after it finishes"
                ) from exc
        else:
            import fcntl

            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError(
                    "Another embedding writer is active; retry after it finishes"
                ) from exc
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def active_snapshot(directory: Path) -> Path:
    pointer = directory / "current.json"
    if not pointer.exists():
        return directory  # Existing flat indexes remain readable.
    value = json.loads(pointer.read_text(encoding="utf-8"))["snapshot"]
    if (
        not isinstance(value, str)
        or not value
        or Path(value).name != value
        or value in {".", ".."}
    ):
        raise ValueError("Invalid embedding snapshot pointer")
    return directory / "snapshots" / value


def new_snapshot(directory: Path) -> Path:
    path = directory / "snapshots" / uuid.uuid4().hex
    path.mkdir(parents=True)
    return path


def publish_snapshot(directory: Path, snapshot: Path) -> None:
    # Each file is closed and fsynced before the pointer can name the generation.
    for name in ("segments.faiss", "segments.mapping.jsonl", "segments.meta.toml"):
        with (snapshot / name).open("rb") as handle:
            os.fsync(handle.fileno())
    _sync_directory(snapshot)
    _sync_directory(snapshot.parent)
    atomic_write_text(
        directory / "current.json", json.dumps({"snapshot": snapshot.name}) + "\n"
    )
    _sync_directory(directory)


def _sync_directory(directory: Path) -> None:
    if os.name != "nt":
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def active_index_metadata(osii_root: Path):
    root = osii_root / "embeddings"
    for path in root.rglob("segments.meta.toml") if root.exists() else []:
        directory = path.parent
        if directory.parent.name == "snapshots":
            namespace = directory.parent.parent
            if active_snapshot(namespace) != directory:
                continue
        elif (directory / "current.json").exists():
            continue  # A migrated flat index is retained only for recovery.
        yield path
