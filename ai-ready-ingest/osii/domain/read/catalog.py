from pathlib import Path
import re
import tomllib


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


def load_folders_catalog(osii_store: Path) -> list[dict]:
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


def load_files_catalog(osii_store: Path) -> list[dict]:
    entries = []
    for path in _folder_manifest_paths(osii_store):
        data = _read_folder_manifest(path)
        if not data:
            continue
        for doc in data.get("docs", []):
            entries.append(
                {
                    "source_relpath": doc.get("source_relpath"),
                    "file_id": doc.get("file_id"),
                }
            )
    return entries


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
