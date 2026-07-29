from datetime import datetime, UTC
from pathlib import Path

import tomli_w

from osii.domain.storage.ids import new_intake_id
from osii.domain.storage.store import root_toml_path


def write_root_toml(
    osii_store: Path,
    root_folder_id: str,
    host_path: str | None = None,
    container_path: str | None = None,
    notes: str | None = None,
    tool_versions: dict | None = None,
) -> Path:
    path = root_toml_path(osii_store)

    payload = {
        "root": {
            "root_id": new_intake_id(),
            "created_utc": datetime.now(UTC).isoformat(),
            "folder_id": root_folder_id,
        },
        "data_root": {
            "host_path": host_path or "",
            "container_path": container_path or "",
            "relpath_convention": "posix",
        },
        "build": {
            "generated_utc": datetime.now(UTC).isoformat(),
        },
    }

    if notes:
        payload["root"]["notes"] = notes

    if tool_versions:
        payload["tool_versions"] = tool_versions

    path.write_text(tomli_w.dumps(payload), encoding="utf-8")
    return path


# Compatibility wrappers for older callers
def write_collection_toml(
    osii_store: Path,
    collection_name: str,
    root_folder_id: str,
    host_path: str | None = None,
    container_path: str | None = None,
    notes: str | None = None,
    config_relpath: str | None = None,
    tool_versions: dict | None = None,
) -> Path:
    return write_root_toml(
        osii_store=osii_store,
        root_folder_id=root_folder_id,
        host_path=host_path,
        container_path=container_path,
        notes=notes,
        tool_versions=tool_versions,
    )


def write_collection_synthesis(
    osii_store: Path,
    collection_name: str,
    root_folder_label: str,
    total_files: int,
    top_level_doc_count: int,
    top_level_subfolder_count: int,
    note: str | None = None,
) -> Path:
    return write_root_synthesis(
        osii_store=osii_store,
        root_label=root_folder_label,
        total_files=total_files,
        top_level_doc_count=top_level_doc_count,
        top_level_subfolder_count=top_level_subfolder_count,
        note=note,
    )