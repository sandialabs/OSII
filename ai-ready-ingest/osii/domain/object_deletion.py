from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import tomllib

import tomli_w

from osii.domain.artifacts.source_files import get_source_file_path
from osii.domain.catalog_db import rebuild_catalog
from osii.domain.processing.jobs import (
    find_active_jobs_for_paths,
    find_job_history_for_paths,
    purge_job_history,
)
from osii.domain.read.docs import get_doc_meta
from osii.domain.scopes.collections import (
    list_collections_for_file,
    remove_document_from_collection,
)
from osii.domain.storage.atomic import atomic_write_text


VALID_MODES = {"sidecar_only", "source_and_sidecar"}


def _folder_impacts(osii_root: Path, file_id: str, source_relpath: str) -> list[dict]:
    impacts: list[dict] = []
    normalized_source = source_relpath.replace("\\", "/").strip("/")
    for path in sorted((osii_root / "folders").glob("folder-*.toml")):
        if path.name.endswith((".overview.toml", ".synth.toml")):
            continue
        try:
            payload = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        node = payload.get("node", {})
        folder_path = str(node.get("path_hint") or "").replace("\\", "/").strip("/")
        direct_member = any(str(item.get("file_id")) == file_id for item in payload.get("docs", []))
        ancestor_scope = not folder_path or normalized_source.startswith(f"{folder_path}/")
        if direct_member or ancestor_scope:
            impacts.append(
                {
                    "folder_id": str(node.get("folder_id") or path.stem.removeprefix("folder-")),
                    "path": str(node.get("path_hint") or ""),
                    "manifest": path.name,
                }
            )
    return impacts


def _aggregate_paths(osii_root: Path, folders: list[dict], collections: list[dict]) -> list[Path]:
    candidates = [
        osii_root / "root.synth.txt",
        osii_root / "root.synth.toml",
        osii_root / "root.overview.toml",
        osii_root / "syntheses",
        osii_root / "enrichments",
    ]
    for folder in folders:
        identifier = folder["folder_id"]
        candidates.extend(
            [
                osii_root / "folders" / f"folder-{identifier}.overview.toml",
                osii_root / "folders" / f"folder-{identifier}.synth.toml",
                osii_root / "folders" / f"folder-{identifier}.synth.txt",
                osii_root / "folders" / f"folder-{identifier}.syntheses",
                osii_root / "folders" / f"folder-{identifier}.enrichments",
            ]
        )
    for collection in collections:
        directory = osii_root / "collections" / collection["id"]
        candidates.extend([directory / "syntheses", directory / "enrichments"])
    return [path for path in candidates if path.exists()]


def _path_size(path: Path) -> tuple[int, int]:
    if path.is_file():
        return 1, path.stat().st_size
    count = 0
    size = 0
    for candidate in path.rglob("*"):
        if candidate.is_file():
            count += 1
            size += candidate.stat().st_size
    return count, size


def build_deletion_preview(
    osii_root: Path,
    shared_root: Path,
    upload_root: Path,
    file_id: str,
    mode: str,
) -> dict | None:
    if mode not in VALID_MODES:
        raise ValueError("mode must be sidecar_only or source_and_sidecar")
    osii_root = osii_root.resolve()
    meta = get_doc_meta(osii_root, file_id)
    object_dir = osii_root / "objects" / file_id
    if meta is None or not object_dir.is_dir():
        return None
    source = get_source_file_path(osii_root, shared_root, upload_root, file_id)
    collections = list_collections_for_file(osii_root, file_id)
    source_relpath = str((meta.get("file", {}) or {}).get("source_relpath") or "")
    folders = _folder_impacts(osii_root, file_id, source_relpath)
    aggregates = _aggregate_paths(osii_root, folders, collections)
    object_count, object_bytes = _path_size(object_dir)
    active_jobs = find_active_jobs_for_paths([source_relpath, str(source) if source else ""])
    history_run_ids = find_job_history_for_paths([source_relpath, str(source) if source else ""])
    index_dir = osii_root / "embeddings"
    index_count, index_bytes = _path_size(index_dir) if index_dir.exists() else (0, 0)
    snapshot = {
        "file_id": file_id,
        "mode": mode,
        "object_file_count": object_count,
        "object_bytes": object_bytes,
        "source_path": str(source) if source else None,
        "source_size_bytes": source.stat().st_size if source else None,
        "source_mtime_ns": source.stat().st_mtime_ns if source else None,
        "collection_ids": sorted(item["id"] for item in collections),
        "folder_ids": sorted(item["folder_id"] for item in folders),
        "aggregate_paths": sorted(str(path.relative_to(osii_root)) for path in aggregates),
        "index_file_count": index_count,
        "index_bytes": index_bytes,
        "active_jobs": active_jobs,
        "history_run_ids": history_run_ids,
    }
    token = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        **snapshot,
        "preview_token": token,
        "collections": [{"id": item["id"], "name": item["name"]} for item in collections],
        "folders": folders,
        "indexes_rebuild_required": index_count > 0,
        "source_will_be_deleted": mode == "source_and_sidecar" and source is not None,
        "source_will_remain": mode == "sidecar_only" and source is not None,
    }


def _remove_folder_memberships(osii_root: Path, file_id: str, folders: list[dict]) -> None:
    for folder in folders:
        path = osii_root / "folders" / folder["manifest"]
        try:
            payload = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        original_docs = payload.get("docs", [])
        payload["docs"] = [item for item in original_docs if str(item.get("file_id")) != file_id]
        removed = len(payload["docs"]) != len(original_docs)
        node = payload.get("node", {})
        stats = node.get("stats")
        if removed and isinstance(stats, dict) and isinstance(stats.get("file_count"), int):
            stats["file_count"] = max(0, stats["file_count"] - 1)
        atomic_write_text(path, tomli_w.dumps(payload))


def delete_object(
    osii_root: Path,
    shared_root: Path,
    upload_root: Path,
    file_id: str,
    *,
    mode: str,
    preview_token: str,
    confirmation: str,
) -> dict:
    preview = build_deletion_preview(osii_root, shared_root, upload_root, file_id, mode)
    if preview is None:
        raise ValueError("unknown file_id")
    if confirmation != file_id:
        raise ValueError("confirmation must exactly match the file ID")
    if preview_token != preview["preview_token"]:
        raise RuntimeError("Deletion preview is stale; review the impact again.")
    if preview["active_jobs"]:
        raise RuntimeError("The file is referenced by an active Intake job. Wait for it to finish before deleting.")

    osii_root = osii_root.resolve()
    source_path = Path(preview["source_path"]) if preview["source_path"] else None
    staged_source: Path | None = None
    if mode == "source_and_sidecar" and source_path is not None:
        staged_source = source_path.with_name(f".{source_path.name}.osii-delete-{file_id[-8:]}")
        if staged_source.exists():
            raise RuntimeError(f"Temporary deletion path already exists: {staged_source.name}")
        try:
            os.replace(source_path, staged_source)
        except OSError as exc:
            raise RuntimeError(
                "The original file could not be moved for deletion. Check source-folder permissions or use OSII-data-only deletion."
            ) from exc
    try:
        for collection in preview["collections"]:
            remove_document_from_collection(osii_root, collection["id"], file_id)
        _remove_folder_memberships(osii_root, file_id, preview["folders"])
        for relpath in preview["aggregate_paths"]:
            target = osii_root / relpath
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink(missing_ok=True)
        shutil.rmtree(osii_root / "objects" / file_id)
        shutil.rmtree(osii_root / "embeddings", ignore_errors=True)
        (osii_root / "embeddings").mkdir(parents=True, exist_ok=True)
        purge_job_history(preview["history_run_ids"])
        rebuild_catalog(osii_root)
    except Exception:
        if staged_source is not None and staged_source.exists() and source_path is not None:
            os.replace(staged_source, source_path)
        raise
    if staged_source is not None:
        staged_source.unlink()
    return {
        "ok": True,
        "file_id": file_id,
        "mode": mode,
        "source_deleted": mode == "source_and_sidecar" and source_path is not None,
        "indexes_rebuild_required": preview["index_file_count"] > 0,
        "invalidated_aggregate_count": len(preview["aggregate_paths"]),
        "purged_activity_run_count": len(preview["history_run_ids"]),
    }
