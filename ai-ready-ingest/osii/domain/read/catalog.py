from pathlib import Path
import re
import sqlite3
import tomllib

from osii.domain.catalog_db import list_documents, list_folders


FOLDER_MANIFEST_RE = re.compile(r"^folder-[A-Za-z0-9_.-]+\.toml$")


def _folder_manifest_paths(osii_store: Path) -> list[Path]:
    folders_dir = (osii_store / "folders").resolve()
    if not folders_dir.exists():
        return []

    paths = []
    for path in folders_dir.iterdir():
        if not path.is_file():
            continue
        if FOLDER_MANIFEST_RE.fullmatch(path.name):
            paths.append(path)

    return sorted(paths)


def _read_folder_manifest(path: Path) -> dict | None:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def scan_folders_catalog(osii_store: Path) -> list[dict]:
    entries = []
    seen_folder_ids = set()
    seen_paths = set()

    for path in _folder_manifest_paths(osii_store):
        data = _read_folder_manifest(path)
        if not data:
            continue
        node = data.get("node", {})

        folder_id = node.get("folder_id")
        folder_path = node.get("path_hint", "")

        if not folder_id:
            continue

        normalized_path = str(folder_path).strip().replace("\\", "/").strip("/")

        if folder_id in seen_folder_ids:
            raise RuntimeError(f"Duplicate folder_id detected in folder catalog: {folder_id}")

        if normalized_path in seen_paths and normalized_path != "":
            raise RuntimeError(f"Duplicate folder path detected in folder catalog: {normalized_path}")

        seen_folder_ids.add(folder_id)
        seen_paths.add(normalized_path)

        entries.append(
            {
                "folder_id": folder_id,
                "path": folder_path,
                "last_seen_utc": node.get("indexed_utc", ""),
            }
        )
    return entries


def scan_files_catalog(osii_store: Path) -> list[dict]:
    entries = []
    seen_file_ids: set[str] = set()
    seen_source_relpaths: set[str] = set()

    def add_entry(source_relpath: str | None, file_id: str | None) -> None:
        if not file_id:
            return
        normalized_relpath = str(source_relpath or "").replace("\\", "/").strip("/")
        if file_id in seen_file_ids:
            return
        if normalized_relpath and normalized_relpath in seen_source_relpaths:
            return
        entries.append(
            {
                "source_relpath": source_relpath,
                "file_id": file_id,
            }
        )
        seen_file_ids.add(file_id)
        if normalized_relpath:
            seen_source_relpaths.add(normalized_relpath)

    for path in _folder_manifest_paths(osii_store):
        data = _read_folder_manifest(path)
        if not data:
            continue
        for doc in data.get("docs", []):
            add_entry(doc.get("source_relpath"), doc.get("file_id"))

    # Extraction commits an object bundle before the end-of-run folder rebuild.
    # Include only completed/partial bundles so Files can update after each
    # document without exposing a text file while an extractor is writing it.
    objects_dir = (osii_store / "objects").resolve()
    if objects_dir.exists():
        for object_path in sorted(objects_dir.iterdir()):
            if not object_path.is_dir():
                continue
            if object_path.name in seen_file_ids:
                continue
            meta_path = object_path / "meta.toml"
            provenance_path = object_path / "provenance.toml"
            if not meta_path.is_file() or not provenance_path.is_file():
                continue
            try:
                meta = tomllib.loads(meta_path.read_text(encoding="utf-8"))
                provenance = tomllib.loads(
                    provenance_path.read_text(encoding="utf-8")
                )
            except Exception:
                continue
            status = provenance.get("provenance", {}).get("status")
            if status not in {"done", "partial"}:
                continue
            add_entry(
                meta.get("file", {}).get("source_relpath"),
                object_path.name,
            )
    return entries


def load_folders_catalog(osii_store: Path) -> list[dict]:
    """Read the derived catalog, retaining a filesystem path during rebuilds."""
    try:
        return list_folders(osii_store)
    except (OSError, sqlite3.DatabaseError, RuntimeError):
        return scan_folders_catalog(osii_store)


def load_files_catalog(osii_store: Path) -> list[dict]:
    """Read the derived catalog in the compatibility shape used by existing APIs."""
    try:
        page = list_documents(osii_store, limit=500)
        entries = page["items"]
        cursor = page["next_cursor"]
        while cursor:
            page = list_documents(osii_store, limit=500, cursor=cursor)
            entries.extend(page["items"])
            cursor = page["next_cursor"]
        return [
            {"source_relpath": item["source_relpath"], "file_id": item["file_id"]}
            for item in entries
        ]
    except (OSError, sqlite3.DatabaseError, RuntimeError, ValueError):
        return scan_files_catalog(osii_store)


def resolve_relpath_to_folder_id(osii_store: Path, relpath: str) -> str | None:
    normalized = relpath.strip().replace("\\", "/").strip("/")
    for entry in load_folders_catalog(osii_store):
        candidate = str(entry.get("path", "")).strip().replace("\\", "/").strip("/")
        if candidate == normalized:
            return entry.get("folder_id")
    return None


def resolve_source_relpath_to_file_id(osii_store: Path, source_relpath: str) -> str | None:
    normalized = source_relpath.strip().replace("\\", "/").strip("/")
    for entry in load_files_catalog(osii_store):
        candidate = str(entry.get("source_relpath", "")).strip().replace("\\", "/").strip("/")
        if candidate == normalized:
            return entry.get("file_id")
    return None
