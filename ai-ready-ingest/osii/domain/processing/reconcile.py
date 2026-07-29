from __future__ import annotations

from pathlib import Path
import tomllib

from osii.domain.processing.intake import expand_queue_to_files
from osii.domain.storage.ids import compute_file_id
from osii.domain.read.catalog import load_files_catalog
from osii.domain.storage.store import meta_toml_path
from osii.domain.processing.pathing import display_rel


def _normalize_relpath(value: str | None) -> str:
    return (value or "").strip().replace("\\", "/").strip("/")


def _load_object_meta(osii_root: Path, file_id: str) -> dict | None:
    path = meta_toml_path(osii_root, file_id)
    if not path.exists():
        return None
    return tomllib.loads(path.read_text(encoding="utf-8"))


def scan_source_files(
    *,
    data_root: Path,
    include_patterns: list[str],
    exclude_patterns: list[str],
    show_hidden: bool = False,
) -> list[Path]:
    queue_items = [
        {
            "path": str(data_root),
            "display": str(data_root),
            "kind": "folder",
            "source": "shared",
        }
    ]

    resolved_files, _ = expand_queue_to_files(
        queue_items=queue_items,
        include_subfolders=True,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        show_hidden=show_hidden,
        max_files=None,
        max_total_size=None,
        shared_root=data_root,
        upload_root=data_root,
    )
    return resolved_files


def reconcile_osii_with_source(
    *,
    osii_root: Path,
    data_root: Path,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    show_hidden: bool = False,
) -> dict:
    include_patterns = include_patterns or []
    exclude_patterns = exclude_patterns or []

    source_files = scan_source_files(
        data_root=data_root,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        show_hidden=show_hidden,
    )

    current_by_relpath = {}
    current_by_file_id = {}

    for path in source_files:
        relpath = path.relative_to(data_root).as_posix()
        file_id = compute_file_id(path)
        current_by_relpath[relpath] = {
            "path": path,
            "file_id": file_id,
        }
        current_by_file_id[file_id] = {
            "path": path,
            "source_relpath": relpath,
        }

    catalog_entries = load_files_catalog(osii_root)

    unchanged = []
    changed = []
    missing_source = []
    new_files = []
    moved = []

    seen_catalog_relpaths = set()

    for entry in catalog_entries:
        source_relpath = _normalize_relpath(entry.get("source_relpath"))
        catalog_file_id = entry.get("file_id")
        seen_catalog_relpaths.add(source_relpath)

        current = current_by_relpath.get(source_relpath)
        if current is not None:
            if current["file_id"] == catalog_file_id:
                unchanged.append(
                    {
                        "source_relpath": source_relpath,
                        "file_id": catalog_file_id,
                    }
                )
            else:
                changed.append(
                    {
                        "source_relpath": source_relpath,
                        "old_file_id": catalog_file_id,
                        "new_file_id": current["file_id"],
                    }
                )
            continue

        if catalog_file_id in current_by_file_id:
            moved_info = current_by_file_id[catalog_file_id]
            moved.append(
                {
                    "old_source_relpath": source_relpath,
                    "new_source_relpath": moved_info["source_relpath"],
                    "file_id": catalog_file_id,
                }
            )
        else:
            missing_source.append(
                {
                    "source_relpath": source_relpath,
                    "file_id": catalog_file_id,
                }
            )

    for relpath, current in current_by_relpath.items():
        if relpath not in seen_catalog_relpaths and current["file_id"] not in {
            item["file_id"] for item in moved
        }:
            new_files.append(
                {
                    "source_relpath": relpath,
                    "file_id": current["file_id"],
                }
            )

    return {
        "summary": {
            "unchanged": len(unchanged),
            "changed": len(changed),
            "moved": len(moved),
            "missing_source": len(missing_source),
            "new_files": len(new_files),
        },
        "unchanged": unchanged,
        "changed": changed,
        "moved": moved,
        "missing_source": missing_source,
        "new_files": new_files,
    }