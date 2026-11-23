"""Bounded source navigation. Only the deployment's mounted root is eligible."""
from pathlib import Path
import os


def resolve_directory(root: Path, relative: str) -> Path:
    root = root.resolve()
    value = Path(relative)
    if value.is_absolute() or any(part.startswith(".") and part != "." for part in value.parts):
        raise ValueError("Select a visible subdirectory within the configured source mount")
    target = (root / value).resolve()
    if not target.is_relative_to(root) or not target.is_dir():
        raise ValueError("Source directory is unavailable or outside the configured mount")
    return target


def browse(root: Path, relative: str, cursor: int = 0, limit: int = 200) -> dict:
    directory = resolve_directory(root, relative)
    if cursor < 0 or not 1 <= limit <= 500:
        raise ValueError("Invalid source page")
    items = []
    truncated = False
    with os.scandir(directory) as entries:
        for entry in entries:
            if entry.name.startswith(".") or entry.is_symlink():
                continue
            if len(items) >= 20000:
                truncated = True
                break
            try:
                kind = "directory" if entry.is_dir(follow_symlinks=False) else "file"
                size = entry.stat(follow_symlinks=False).st_size if kind == "file" else None
                items.append({"name": entry.name, "path": (directory / entry.name).relative_to(root.resolve()).as_posix(),
                    "kind": kind, "size_bytes": size, "readable": os.access(entry.path, os.R_OK)})
            except OSError:
                continue
    items.sort(key=lambda item: (item["kind"] != "directory", item["name"].casefold()))
    return {"path": directory.relative_to(root.resolve()).as_posix(), "items": items[cursor:cursor+limit],
        "next_cursor": cursor+limit if cursor+limit < len(items) else None, "truncated": truncated}
