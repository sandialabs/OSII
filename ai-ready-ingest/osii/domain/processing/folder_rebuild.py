from __future__ import annotations

import shutil
from pathlib import Path

from osii.domain.storage.folder_ids import (
    get_or_create_folder_id_for_relpath,
    load_folder_id_registry,
    save_folder_id_registry,
)
from osii.domain.storage.folders import folder_stats, write_folder_manifest
from osii.domain.storage.ids import compute_file_id


def relpath_under(root: Path, path: Path) -> str:
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
        return "" if rel == "." else rel
    except Exception:
        return path.name


def clear_folder_manifests(osii_store: Path) -> int:
    folders_dir = (osii_store / "folders").resolve()
    if not folders_dir.exists():
        return 0

    removed = 0

    for pattern in (
        "folder-*.toml",
        "folder-*.overview.toml",
        "folder-*.synth.toml",
        "folder-*.synth.txt",
    ):
        for path in folders_dir.glob(pattern):
            path.unlink()
            removed += 1

    for pattern in ("folder-*.syntheses", "folder-*.enrichments"):
        for path in folders_dir.glob(pattern):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
                removed += 1

    # intentionally do not remove folder_ids.toml
    return removed


def build_folder_artifacts(
    *,
    resolved_files: list[Path],
    data_volume_root: Path,
    shared_root: Path,
    osii_store: Path,
    root_folder_id: str,
    clear_existing: bool = True,
) -> tuple[int, int, dict[str, str], list[Path]]:
    if clear_existing:
        clear_folder_manifests(osii_store)

    folders_to_docs: dict[str, list[Path]] = {}
    folders_to_subfolders: dict[str, set[Path]] = {}
    all_folders: set[Path] = set()

    for file_path in resolved_files:
        parent = file_path.parent.resolve()
        all_folders.add(parent)

        cursor = parent
        while True:
            all_folders.add(cursor)
            if cursor == shared_root.resolve():
                break
            if cursor.parent == cursor:
                break
            cursor = cursor.parent.resolve()

    for folder in all_folders:
        folders_to_docs[str(folder)] = []
        folders_to_subfolders[str(folder)] = set()

    for file_path in resolved_files:
        folders_to_docs[str(file_path.parent.resolve())].append(file_path.resolve())

    for folder in all_folders:
        if folder == shared_root.resolve():
            continue
        parent = folder.parent.resolve()
        if str(parent) in folders_to_subfolders:
            folders_to_subfolders[str(parent)].add(folder)

    registry = load_folder_id_registry(osii_store)

    folder_id_map: dict[str, str] = {}
    for folder in sorted(all_folders):
        relpath = relpath_under(shared_root, folder)

        if folder == shared_root.resolve():
            registry[""] = root_folder_id
            folder_id_map[str(folder)] = root_folder_id
        else:
            folder_id, registry = get_or_create_folder_id_for_relpath(
                osii_store,
                relpath,
                registry=registry,
            )
            folder_id_map[str(folder)] = folder_id

    save_folder_id_registry(osii_store, registry)

    seen_folder_ids = set()
    seen_paths = set()

    for folder in sorted(all_folders):
        folder_id = folder_id_map[str(folder)]
        relpath = relpath_under(shared_root, folder)
        path_hint = relpath

        if folder_id in seen_folder_ids:
            raise RuntimeError(f"Folder rebuild attempted to reuse folder_id for multiple paths: {folder_id}")

        normalized_path = path_hint.strip().replace("\\", "/").strip("/")
        if normalized_path in seen_paths and normalized_path != "":
            raise RuntimeError(f"Folder rebuild attempted to write duplicate folder path: {normalized_path}")

        seen_folder_ids.add(folder_id)
        seen_paths.add(normalized_path)

        direct_docs = folders_to_docs[str(folder)]
        direct_subfolders = sorted(list(folders_to_subfolders[str(folder)]), key=lambda p: p.name.lower())

        docs_payload = []
        for doc in sorted(direct_docs, key=lambda p: p.name.lower()):
            docs_payload.append(
                {
                    "source_relpath": relpath_under(data_volume_root, doc),
                    "file_id": compute_file_id(doc),
                }
            )

        subfolders_payload = []
        for sub in direct_subfolders:
            subfolders_payload.append(
                {
                    "folder_id": folder_id_map[str(sub)],
                    "path_hint": relpath_under(shared_root, sub),
                }
            )

        stats = folder_stats(direct_docs, direct_subfolders)

        write_folder_manifest(
            osii_store=osii_store,
            folder_id=folder_id,
            path_hint=path_hint,
            docs=docs_payload,
            subfolders=subfolders_payload,
            stats=stats,
            entrypoints={
                "recommended_file_ids": [d["file_id"] for d in docs_payload[:3]]
            } if docs_payload else None,
        )

    root_direct_docs = folders_to_docs.get(str(shared_root.resolve()), [])
    root_direct_subfolders = list(folders_to_subfolders.get(str(shared_root.resolve()), set()))
    return len(root_direct_docs), len(root_direct_subfolders), folder_id_map, sorted(all_folders)