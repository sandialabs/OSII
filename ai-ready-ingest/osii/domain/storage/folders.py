from datetime import datetime, UTC
from pathlib import Path
import tomllib

import tomli_w
from osii.domain.storage.atomic import atomic_write_text

from osii.domain.storage.ids import new_folder_id
from osii.domain.storage.store import folder_manifest_path


def _all_folder_manifest_paths(osii_store: Path) -> list[Path]:
    folders_dir = (osii_store / "folders").resolve()
    if not folders_dir.exists():
        return []
    return sorted(folders_dir.glob("folder-*.toml"))


def get_or_create_folder_id(osii_store: Path, relpath: str) -> str:
    normalized = relpath.strip().replace("\\", "/").strip("/")

    for path in _all_folder_manifest_paths(osii_store):
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            node = data.get("node", {})
            candidate = str(node.get("path_hint", "")).strip().replace("\\", "/").strip("/")
            folder_id = node.get("folder_id")
            if candidate == normalized and folder_id:
                return folder_id
        except Exception:
            continue

    return new_folder_id()


def write_folder_manifest(
    osii_store: Path,
    folder_id: str,
    path_hint: str,
    docs: list[dict],
    subfolders: list[dict],
    stats: dict | None = None,
    entrypoints: dict | None = None,
) -> Path:
    path = folder_manifest_path(osii_store, folder_id)

    payload = {
        "node": {
            "folder_id": folder_id,
            "path_hint": path_hint,
            "indexed_utc": datetime.now(UTC).isoformat(),
            "summary_relpath": f"folder-{folder_id}.summary.osii.txt",
        },
        "docs": docs,
        "subfolders": subfolders,
    }

    if stats:
        payload["node"]["stats"] = stats

    if entrypoints:
        payload["entrypoints"] = entrypoints

    return atomic_write_text(path, tomli_w.dumps(payload))



def folder_stats(
    direct_docs: list[Path],
    direct_subfolders: list[Path],
) -> dict:
    total_bytes = 0
    latest_mtime = None

    for p in direct_docs:
        try:
            size = p.stat().st_size
            total_bytes += size
            mtime = datetime.fromtimestamp(p.stat().st_mtime, UTC)
            if latest_mtime is None or mtime > latest_mtime:
                latest_mtime = mtime
        except Exception:
            continue

    return {
        "file_count": len(direct_docs),
        "subfolder_count": len(direct_subfolders),
        "total_bytes": total_bytes,
        "latest_mtime_utc": latest_mtime.isoformat() if latest_mtime else "",
    }
