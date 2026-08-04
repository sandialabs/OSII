import json
from datetime import datetime, UTC
from pathlib import Path

import tomli_w
import tomllib
from osii.domain.storage.atomic import atomic_write_text

from osii.domain.storage.store import (
    artifacts_dir,
    manifest_jsonl_path,
    meta_toml_path,
    object_dir,
    provenance_path
)


def iso_mtime_utc(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
    except Exception:
        return None


def ensure_object_bundle(osii_store: Path, file_id: str) -> Path:
    obj_dir = object_dir(osii_store, file_id)
    obj_dir.mkdir(parents=True, exist_ok=True)
    # Remove the segment directory
    artifacts_dir(osii_store, file_id).mkdir(parents=True, exist_ok=True)
    return obj_dir


def write_meta_toml(
    osii_store: Path,
    file_id: str,
    source_relpath: str,
    filename: str,
    mime: str,
    size_bytes: int | None,
    mtime_utc: str | None,
    sha256_hex: str,
    extra_meta: dict | None = None,
) -> Path:
    ensure_object_bundle(osii_store, file_id)
    path = meta_toml_path(osii_store, file_id)

    payload = {
        "file": {
            "source_relpath": source_relpath,
            "filename": filename,
            "mime": mime,
            "size_bytes": size_bytes,
            "mtime_utc": mtime_utc,
        },
        "hash": {
            "sha256": sha256_hex,
        },
    }

    if extra_meta:
        payload["meta"] = extra_meta

    return atomic_write_text(path, tomli_w.dumps(payload))


def write_provenance_toml(
    osii_store: Path,
    file_id: str,
    pipeline_version: str,
    *,
    status: str,
    extractor_name: str,
    extractor_version: str,
    tools: dict | None = None,
    config: dict | None = None,
    counts: dict | None = None,
    errors: dict | None = None,
) -> Path:
    ensure_object_bundle(osii_store, file_id)
    path = provenance_path(osii_store, file_id)

    payload = {
        "provenance": {
            "generated_utc": datetime.now(UTC).isoformat(),
            "pipeline_version": pipeline_version,
            "status": status,
        },
        "extractor": {
            "name": extractor_name,
            "version": extractor_version,
        },
    }

    if tools:
        payload["tools"] = {k: v for k, v in tools.items() if v is not None}

    if config:
        payload["config"] = {k: v for k, v in config.items() if v is not None}

    if counts:
        payload["counts"] = {k: v for k, v in counts.items() if v is not None}

    if errors:
        payload["errors"] = {k: v for k, v in errors.items() if v is not None}

    return atomic_write_text(path, tomli_w.dumps(payload))


def update_synthesis_provenance(
    osii_store: Path,
    file_id: str,
    *,
    synthesizer_name: str,
    synthesizer_version: str,
    config: dict | None = None,
    expert_context_used: bool = False,
) -> Path:
    ensure_object_bundle(osii_store, file_id)
    path = provenance_path(osii_store, file_id)

    payload = {}
    if path.exists():
        payload = tomllib.loads(path.read_text(encoding="utf-8"))

    payload["synthesis"] = {
        "name": synthesizer_name,
        "version": synthesizer_version,
        "generated_utc": datetime.now(UTC).isoformat(),
        "expert_context_used": bool(expert_context_used),
    }

    if config:
        payload["synthesis"]["config"] = {
            k: v for k, v in config.items() if v is not None
        }

    return atomic_write_text(path, tomli_w.dumps(payload))


def append_manifest_record(osii_store: Path, file_id: str, record: dict) -> Path:
    ensure_object_bundle(osii_store, file_id)
    path = manifest_jsonl_path(osii_store, file_id)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def read_manifest_records(osii_store: Path, file_id: str) -> list[dict]:
    path = manifest_jsonl_path(osii_store, file_id)
    if not path.exists():
        return []
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        items.append(json.loads(line))
    return items


def segments_text_path(osii_store: Path, file_id: str) -> Path:
    return (osii_store, file_id) / "text.txt"


def write_segments_text(osii_store: Path, file_id: str, text: str) -> Path:
    ensure_object_bundle(osii_store, file_id)
    path = segments_text_path(osii_store, file_id)
    path.write_text(text, encoding="utf-8")
    return path


def append_segments_text(osii_store: Path, file_id: str, text: str) -> tuple[Path, int, int]:
    ensure_object_bundle(osii_store, file_id)
    path = segments_text_path(osii_store, file_id)

    existing = ""
    if path.exists():
        existing = path.read_text(encoding="utf-8")

    char_start = len(existing)
    new_text = existing + text
    path.write_text(new_text, encoding="utf-8")
    char_end = len(new_text)

    return path, char_start, char_end


# Backward-compatible helper for older extractors
def write_segment_text(osii_store: Path, file_id: str, seg: int, text: str, suffix: str = ".txt") -> Path:
    ensure_object_bundle(osii_store, file_id)
    filename = f"seg-{seg:06d}{suffix}"
    path = (osii_store, file_id) / filename
    path.write_text(text, encoding="utf-8")
    return path


def write_artifact_bytes(
    osii_store: Path,
    file_id: str,
    artifact_num: int,
    extension: str,
    data: bytes,
) -> Path:
    ensure_object_bundle(osii_store, file_id)
    ext = extension if extension.startswith(".") else f".{extension}"
    filename = f"artifact-{artifact_num:06d}{ext}"
    path = artifacts_dir(osii_store, file_id) / filename
    path.write_bytes(data)
    return path

def object_text_path(osii_store: Path, file_id: str) -> Path:
    return object_dir(osii_store, file_id) / "text.txt"


def append_text_file(osii_store: Path, file_id: str, text: str) -> tuple[int, int]:
    ensure_object_bundle(osii_store, file_id)
    path = object_text_path(osii_store, file_id)

    existing = ""
    if path.exists():
        existing = path.read_text(encoding="utf-8")

    char_start = len(existing)
    new_text = existing + text
    path.write_text(new_text, encoding="utf-8")
    char_end = len(new_text)

    return char_start, char_end

def write_text_file(osii_store: Path, file_id: str, text: str) -> Path:
    ensure_object_bundle(osii_store, file_id)
    path = object_text_path(osii_store, file_id)
    path.write_text(text, encoding="utf-8")
    return path

def object_text_path(osii_store: Path, file_id: str) -> Path:
    return object_dir(osii_store, file_id) / "text.txt"
