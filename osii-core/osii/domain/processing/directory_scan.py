"""Bounded filesystem enumeration shared by local and hosted inventory workers.

Only directory entries and stat metadata are read. No persistence, contents,
hashing, processors, or model services are available here.
"""

from __future__ import annotations
import os
import fnmatch
from contextlib import contextmanager
from pathlib import Path
import stat
import time
import uuid


class InterruptedRun(Exception):
    """Control changed or coordinator lease was lost; replay unfinished work."""


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


def directory_batches(
    source: dict, relative: str, options: dict, stopping, *, batch_size: int = 500
):
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
                if len(rows) >= batch_size:
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


def reader(source, relative, options, output):
    import threading

    try:
        for message in directory_batches(source, relative, options, threading.Event()):
            output.put(message)
    except Exception as exc:
        output.put(("error", f"Directory reader failed ({type(exc).__name__})", None))


def stop_reader(process, channel):
    if process.is_alive():
        process.terminate()
    process.join(timeout=0.5)
    if process.is_alive():
        process.kill()
        process.join(timeout=0.5)
    channel.close()
    channel.cancel_join_thread()
    return not process.is_alive()
