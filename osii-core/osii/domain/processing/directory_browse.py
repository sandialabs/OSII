"""Short-lived, isolated directory cursors; no recursion or catalog/content reads."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
import multiprocessing
import os
from pathlib import Path
import time
import uuid

from .source_access import resolve_intake_path


def _reader(
    connection: Connection,
    raw: str | None,
    source: str,
    uploads: str,
    mode: str,
    host: str,
    hidden: bool,
) -> None:
    try:
        current = resolve_intake_path(
            raw, Path(source), Path(uploads), filesystem_mode=mode, host_root=host
        )
        with os.scandir(current) as iterator:
            while connection.poll(45):
                limit = connection.recv()
                entries = []
                exhausted = False
                # Bound inspected entries too, including hidden/unreadable entries.
                for _ in range(limit):
                    child = next(iterator, None)
                    if child is None:
                        exhausted = True
                        break
                    if not hidden and child.name.startswith("."):
                        continue
                    item = {"name": child.name, "path": child.path, "size_bytes": None}
                    try:
                        item["type"] = (
                            "link"
                            if child.is_symlink()
                            else "folder"
                            if child.is_dir(follow_symlinks=False)
                            else "file"
                            if child.is_file(follow_symlinks=False)
                            else "unavailable"
                        )
                        if item["type"] == "unavailable":
                            item["error"] = "Not a regular file"
                        if item["type"] == "file":
                            item["size_bytes"] = child.stat(
                                follow_symlinks=False
                            ).st_size
                    except OSError as exc:
                        item.update(type="unavailable", error=str(exc))
                    entries.append(item)
                parent = str(current.parent) if current.parent != current else None
                if mode == "mounted" and current in (Path(source), Path(uploads)):
                    parent = None
                connection.send(
                    {
                        "current_path": str(current),
                        "parent_path": parent,
                        "entries": entries,
                        "has_more": not exhausted,
                    }
                )
                if exhausted:
                    break
    except (OSError, ValueError) as exc:
        code = (
            403
            if isinstance(exc, PermissionError)
            else 404
            if isinstance(exc, FileNotFoundError)
            else 422
        )
        connection.send({"error": f"Cannot browse this folder: {exc}", "status": code})
    finally:
        connection.close()


class DirectoryBrowsers:
    """API-owned cursors expire after idle time and never restart enumeration to page."""

    def __init__(self) -> None:
        self.sessions: dict[
            str, tuple[BaseProcess, Connection, float, asyncio.Lock]
        ] = {}
        self.retired: list[BaseProcess] = []

    def close_all(self) -> None:
        for token in list(self.sessions):
            self.close(token)

    def close(self, token: str) -> None:
        session = self.sessions.pop(token, None)
        if session:
            process, connection, _, _ = session
            connection.close()
            if process.is_alive():
                process.terminate()
            process.join(timeout=0.05)
            if process.is_alive():
                self.retired.append(process)

    def open(
        self,
        raw: str | None,
        source: Path,
        uploads: Path,
        mode: str,
        host: str,
        hidden: bool,
    ) -> str:
        for token, (process, _, touched, _) in list(self.sessions.items()):
            if not process.is_alive() or time.monotonic() - touched > 45:
                self.close(token)
        self.retired = [process for process in self.retired if process.is_alive()]
        if len(self.sessions) + len(self.retired) >= 8:
            raise ValueError(
                "Too many open folder browsers. Close another browser and retry."
            )
        context = multiprocessing.get_context("spawn")
        connection, child = context.Pipe()
        process = context.Process(
            target=_reader,
            args=(child, raw, str(source), str(uploads), mode, host, hidden),
            daemon=True,
        )
        process.start()
        child.close()
        token = uuid.uuid4().hex
        self.sessions[token] = (process, connection, time.monotonic(), asyncio.Lock())
        return token

    async def page(
        self,
        token: str,
        limit: int,
        disconnected: Callable[[], Awaitable[bool]],
        timeout: float = 15,
    ) -> dict:
        if token not in self.sessions:
            raise KeyError("Folder browser expired. Open the folder again.")
        process, connection, touched, lock = self.sessions[token]
        if time.monotonic() - touched > 45 or not process.is_alive():
            self.close(token)
            raise KeyError("Folder browser expired. Open the folder again.")
        async with lock:
            if token not in self.sessions:
                raise KeyError("Folder browser closed. Open the folder again.")
            self.sessions[token] = (process, connection, time.monotonic(), lock)
            try:
                connection.send(limit)
                started = time.monotonic()
                while not connection.poll():
                    if await disconnected():
                        raise InterruptedError("Folder browsing cancelled")
                    if time.monotonic() - started > timeout:
                        raise TimeoutError(
                            "Folder is not responding. Check the share connection or choose another path."
                        )
                    await asyncio.sleep(0.03)
                result = connection.recv()
                result["cursor"] = token if result.get("has_more") else None
                if not result.get("has_more"):
                    self.close(token)
                return result
            except BaseException:
                self.close(token)
                raise
