from datetime import datetime, UTC
from pathlib import Path

import tomli_w

from osii.domain.storage.ids import new_intake_id
from osii.domain.storage.store import root_toml_path
from osii.domain.storage.synth import write_root_synth


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
    document_word = "document" if total_files == 1 else "documents"
    folder_word = "subfolder" if top_level_subfolder_count == 1 else "subfolders"
    text = (
        f"{root_folder_label} contains {total_files} {document_word}, "
        f"including {top_level_doc_count} at the top level and "
        f"{top_level_subfolder_count} top-level {folder_word}."
    )
    if note:
        text = f"{text}\n\nContext: {note}"
    _, path = write_root_synth(
        osii_root=osii_store,
        synthesis=text,
        kind="deterministic-folder-inventory",
        quality="local",
    )
    return path
