"""One launcher owns a local library; the OS releases ownership after a crash."""

from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO


class LibraryLock:
    def __init__(self, root: Path):
        self.path = root.resolve() / "state" / "application.lock"
        self._file: BinaryIO | None = None

    def acquire(self) -> "LibraryLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            # Windows locks an existing byte. Never truncate, replace, or unlink
            # this file: another process may still own the original file object.
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise RuntimeError("This library is already open in OSII. Close the other instance first.") from exc
        self._file = handle
        return self

    def close(self) -> None:
        if self._file is None:
            return
        if os.name == "nt":
            import msvcrt
            self._file.seek(0)
            msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
        self._file.close()
        self._file = None

    def __enter__(self) -> "LibraryLock":
        return self.acquire()

    def __exit__(self, *_: object) -> None:
        self.close()
