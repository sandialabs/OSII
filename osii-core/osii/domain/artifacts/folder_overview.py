from pathlib import Path
import tomllib

from osii.domain.read.folders import get_folder_manifest
from osii.domain.read.synthesis import get_synth_text
from osii.domain.read.folder_synthesis import get_folder_synthesis_text
from osii.domain.storage.store import object_dir
from osii.domain.storage.synth import write_folder_overview


def read_object_synth_toml(osii_root: Path, file_id: str) -> dict | None:
    path = object_dir(osii_root, file_id) / "synth.toml"
    if not path.exists():
        return None
    return tomllib.loads(path.read_text(encoding="utf-8"))


def read_folder_synth_toml(osii_root: Path, folder_id: str) -> dict | None:
    path = (osii_root / "folders" / f"folder-{folder_id}.synth.toml").resolve()
    if not path.exists():
        return None
    return tomllib.loads(path.read_text(encoding="utf-8"))


def build_folder_overview(osii_root: Path, folder_id: str) -> dict:
    manifest = get_folder_manifest(osii_root, folder_id)
    if manifest is None:
        raise RuntimeError(f"Folder manifest not found: {folder_id}")

    node = manifest.get("node", {})
    docs = manifest.get("docs", [])
    subfolders = manifest.get("subfolders", [])

    overview = {
        "node": {
            "folder_id": folder_id,
            "path": node.get("path_hint", ""),
        },
        "counts": {
            "direct_doc_count": len(docs),
            "direct_subfolder_count": len(subfolders),
            "total_size_bytes": node.get("stats", {}).get("total_bytes"),
        },
        "documents": [],
        "child_folders": [],
    }

    for doc in docs:
        file_id = doc.get("file_id")
        if not file_id:
            continue

        synth = read_object_synth_toml(osii_root, file_id)
        if not synth:
            continue

        doc_entry = {
            "file_id": file_id,
            "filename": synth.get("path", {}).get("source_relpath", "").split("/")[-1],
            "synthesis": synth.get("synthesis", {}).get("synthesis", ""),
            "doc_type": synth.get("synthesis", {}).get("doc_type", "unknown"),
            "quality": synth.get("synthesis", {}).get("quality", "default"),
        }
        overview["documents"].append(doc_entry)

    for sub in subfolders:
        child_folder_id = sub.get("folder_id")
        if not child_folder_id:
            continue

        synth = read_folder_synth_toml(osii_root, child_folder_id)
        if not synth:
            continue

        child_entry = {
            "folder_id": child_folder_id,
            "path": sub.get("path_hint", ""),
            "synthesis": synth.get("synthesis", {}).get("synthesis", ""),
            "kind": synth.get("synthesis", {}).get("kind", "folder"),
            "quality": synth.get("synthesis", {}).get("quality", "default"),
        }
        overview["child_folders"].append(child_entry)

    write_folder_overview(osii_root, folder_id, overview)
    return overview