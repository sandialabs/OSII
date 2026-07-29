import fnmatch
from pathlib import Path

from .pathing import display_rel, path_within


def is_hidden(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts)


def parse_patterns(raw: str) -> list[str]:
    return [line.strip() for line in raw.splitlines() if line.strip()]


def human_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def match_any(rel_path: str, patterns: list[str]) -> bool:
    if not patterns:
        return True
    rel_posix = rel_path.replace("\\", "/")
    return any(fnmatch.fnmatch(rel_posix, pattern) for pattern in patterns)


def excluded(rel_path: str, patterns: list[str]) -> bool:
    rel_posix = rel_path.replace("\\", "/")
    return any(fnmatch.fnmatch(rel_posix, pattern) for pattern in patterns)


def serialize_queue_items(paths: list[Path], shared_root: Path, upload_root: Path) -> list[dict]:
    items = []
    seen = set()

    for path in paths:
        p = path.resolve()
        key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "path": str(p),
                "display": display_rel(p, shared_root, upload_root),
                "kind": "folder" if p.is_dir() else "file",
                "source": "shared" if path_within(shared_root, p) else "upload",
            }
        )
    return items


def expand_queue_to_files(
    queue_items: list[dict],
    include_subfolders: bool,
    include_patterns: list[str],
    exclude_patterns: list[str],
    show_hidden: bool,
    max_files: int | None,
    max_total_size: int | None,
    shared_root: Path,
    upload_root: Path,
) -> tuple[list[Path], dict]:
    resolved_files: list[Path] = []
    seen = set()
    total_size = 0
    stopped_reason = None

    for item in queue_items:
        p = Path(item["path"]).resolve()
        if not p.exists():
            continue

        if p.is_file():
            candidates = [p]
        elif p.is_dir():
            iterator = p.rglob("*") if include_subfolders else p.glob("*")
            candidates = [c for c in iterator if c.is_file()]
        else:
            continue

        for f in candidates:
            try:
                rel_hidden = f.relative_to(f.anchor) if f.is_absolute() else f
            except Exception:
                rel_hidden = f

            if not show_hidden and is_hidden(rel_hidden):
                continue

            if path_within(shared_root, f):
                rel = f.relative_to(shared_root).as_posix()
            elif path_within(upload_root, f):
                rel = f.relative_to(upload_root).as_posix()
            else:
                rel = f.name

            if include_patterns and not match_any(rel, include_patterns):
                continue
            if exclude_patterns and excluded(rel, exclude_patterns):
                continue

            key = str(f.resolve()).lower()
            if key in seen:
                continue

            try:
                size = f.stat().st_size
            except Exception:
                continue

            if max_files is not None and len(resolved_files) >= max_files:
                stopped_reason = f"Stopped after reaching max files limit ({max_files})."
                return resolved_files, {
                    "matched_count": len(resolved_files),
                    "total_size": total_size,
                    "total_size_human": human_size(total_size),
                    "sample": [
                        {"path": str(p), "display": display_rel(p, shared_root, upload_root)}
                        for p in resolved_files[:50]
                    ],
                    "stopped_reason": stopped_reason,
                }

            if max_total_size is not None and total_size + size > max_total_size:
                stopped_reason = f"Stopped after reaching max total size limit ({human_size(max_total_size)})."
                return resolved_files, {
                    "matched_count": len(resolved_files),
                    "total_size": total_size,
                    "total_size_human": human_size(total_size),
                    "sample": [
                        {"path": str(p), "display": display_rel(p, shared_root, upload_root)}
                        for p in resolved_files[:50]
                    ],
                    "stopped_reason": stopped_reason,
                }

            seen.add(key)
            resolved_files.append(f)
            total_size += size

    preview = {
        "matched_count": len(resolved_files),
        "total_size": total_size,
        "total_size_human": human_size(total_size),
        "sample": [
            {"path": str(p), "display": display_rel(p, shared_root, upload_root)}
            for p in resolved_files[:50]
        ],
        "stopped_reason": stopped_reason,
    }
    return resolved_files, preview