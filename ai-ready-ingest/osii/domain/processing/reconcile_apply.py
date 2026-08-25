from __future__ import annotations

from pathlib import Path
import tomllib

import tomli_w

from osii.domain.processing.folder_rebuild import build_folder_artifacts
from osii.domain.processing.extractor_selection import choose_extractor_for_path, load_extractor_routes
from osii.domain.processing.source_status import write_source_status
from osii.domain.storage.root_descriptor import write_root_toml
from osii.domain.storage.folders import get_or_create_folder_id
from osii.domain.storage.store import ensure_osii_store_layout, meta_toml_path
from osii.domain.storage.atomic import atomic_write_text
from osii.extraction.dispatcher import dispatch_extract


def _update_meta_source_relpath(osii_root: Path, file_id: str, new_source_relpath: str) -> bool:
    path = meta_toml_path(osii_root, file_id)
    if not path.exists():
        return False

    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    payload.setdefault("file", {})
    payload["file"]["source_relpath"] = new_source_relpath
    payload["file"]["filename"] = Path(new_source_relpath).name

    atomic_write_text(path, tomli_w.dumps(payload))
    return True


def _resolve_extractor_name(src: Path, extractor_name: str | None, extractor_routes: list[dict]) -> str:
    if extractor_name:
        return extractor_name
    return choose_extractor_for_path(src, extractor_routes)


def _resolve_source_path(
    source_root: Path,
    data_volume_root: Path,
    source_relpath: str,
) -> Path | None:
    """Resolve a canonical data-volume path while keeping it inside source_root."""
    normalized_source_root = source_root.resolve()
    for base in (data_volume_root.resolve(), normalized_source_root):
        candidate = (base / source_relpath).resolve()
        try:
            candidate.relative_to(normalized_source_root)
        except ValueError:
            continue
        if candidate.is_file():
            return candidate
    return None


def apply_source_path_reconciliation(
    *,
    reconcile_result: dict,
    osii_root: Path,
    source_root: Path,
    data_volume_root: Path | None = None,
    rebuild_folders: bool = True,
) -> dict:
    """Apply path/status repairs without extracting new or changed files."""
    ensure_osii_store_layout(osii_root)
    volume_root = (data_volume_root or source_root).resolve()
    applied = {
        "moved_updated": 0,
        "missing_marked": 0,
        "changed_marked": 0,
        "active_marked": 0,
        "folder_tree_rebuilt": False,
    }

    recognized_paths: list[Path] = []
    for item in reconcile_result.get("unchanged", []):
        write_source_status(
            osii_root,
            item["file_id"],
            status="active",
            source_relpath=item["source_relpath"],
        )
        applied["active_marked"] += 1
        resolved = _resolve_source_path(
            source_root,
            volume_root,
            item["source_relpath"],
        )
        if resolved is not None:
            recognized_paths.append(resolved)

    for item in reconcile_result.get("moved", []):
        new_relpath = item["new_source_relpath"]
        file_id = item["file_id"]
        if _update_meta_source_relpath(osii_root, file_id, new_relpath):
            applied["moved_updated"] += 1
        write_source_status(
            osii_root,
            file_id,
            status="active",
            source_relpath=new_relpath,
        )
        applied["active_marked"] += 1
        resolved = _resolve_source_path(source_root, volume_root, new_relpath)
        if resolved is not None:
            recognized_paths.append(resolved)

    for item in reconcile_result.get("missing_source", []):
        write_source_status(
            osii_root,
            item["file_id"],
            status="missing_source",
            source_relpath=item["source_relpath"],
        )
        applied["missing_marked"] += 1

    for item in reconcile_result.get("changed", []):
        write_source_status(
            osii_root,
            item["old_file_id"],
            status="source_changed",
            source_relpath=item["source_relpath"],
        )
        applied["changed_marked"] += 1

    if rebuild_folders:
        root_folder_id = get_or_create_folder_id(osii_root, "")
        write_root_toml(
            osii_root,
            root_folder_id=root_folder_id,
            host_path=str(source_root.resolve()),
            container_path=str(source_root.resolve()),
            notes="source path rescan",
            tool_versions={"pipeline_version": "osii-v1-draft"},
        )
        build_folder_artifacts(
            resolved_files=sorted(set(recognized_paths)),
            data_volume_root=volume_root,
            shared_root=source_root.resolve(),
            osii_store=osii_root,
            root_folder_id=root_folder_id,
        )
        applied["folder_tree_rebuilt"] = True

    return applied


def apply_reconciliation(
    *,
    reconcile_result: dict,
    osii_root: Path,
    data_root: Path,
    extractor_name: str | None = None,
    expert_context: str | None = None,
    rebuild_folders: bool = True,
) -> dict:
    ensure_osii_store_layout(osii_root)
    extractor_routes = load_extractor_routes()

    applied = {
        "moved_updated": 0,
        "reextracted_changed": 0,
        "extracted_new": 0,
        "missing_marked": 0,
        "active_marked": 0,
        "folder_tree_rebuilt": False,
    }

    for item in reconcile_result.get("unchanged", []):
        write_source_status(
            osii_root,
            item["file_id"],
            status="active",
            source_relpath=item["source_relpath"],
        )
        applied["active_marked"] += 1

    for item in reconcile_result.get("moved", []):
        new_relpath = item["new_source_relpath"]
        file_id = item["file_id"]

        ok = _update_meta_source_relpath(osii_root, file_id, new_relpath)
        if ok:
            applied["moved_updated"] += 1

        write_source_status(
            osii_root,
            file_id,
            status="active",
            source_relpath=new_relpath,
        )
        applied["active_marked"] += 1

    for item in reconcile_result.get("missing_source", []):
        write_source_status(
            osii_root,
            item["file_id"],
            status="missing_source",
            source_relpath=item["source_relpath"],
        )
        applied["missing_marked"] += 1

    for item in reconcile_result.get("changed", []):
        src = (data_root / item["source_relpath"]).resolve()
        if src.exists():
            resolved_extractor_name = _resolve_extractor_name(src, extractor_name, extractor_routes)
            dispatch_extract(
                extractor_name=resolved_extractor_name,
                source_path=src,
                data_volume_root=data_root,
                osii_store=osii_root,
                expert_context=expert_context,
                extractor_config={},
            )
            write_source_status(
                osii_root,
                item["new_file_id"],
                status="active",
                source_relpath=item["source_relpath"],
            )
            applied["reextracted_changed"] += 1
            applied["active_marked"] += 1

    for item in reconcile_result.get("new_files", []):
        src = (data_root / item["source_relpath"]).resolve()
        if src.exists():
            resolved_extractor_name = _resolve_extractor_name(src, extractor_name, extractor_routes)
            dispatch_extract(
                extractor_name=resolved_extractor_name,
                source_path=src,
                data_volume_root=data_root,
                osii_store=osii_root,
                expert_context=expert_context,
                extractor_config={},
            )
            write_source_status(
                osii_root,
                item["file_id"],
                status="active",
                source_relpath=item["source_relpath"],
            )
            applied["extracted_new"] += 1
            applied["active_marked"] += 1

    if rebuild_folders:
        resolved_files = [p.resolve() for p in data_root.rglob("*") if p.is_file()]

        root_folder_id = get_or_create_folder_id(osii_root, "")
        write_root_toml(
            osii_root,
            root_folder_id=root_folder_id,
            host_path=str(data_root),
            container_path=str(data_root),
            notes="rescan apply",
            tool_versions={"pipeline_version": "osii-v1-draft"},
        )

        build_folder_artifacts(
            resolved_files=resolved_files,
            data_volume_root=data_root,
            shared_root=data_root,
            osii_store=osii_root,
            root_folder_id=root_folder_id,
        )
        applied["folder_tree_rebuilt"] = True

    return applied
