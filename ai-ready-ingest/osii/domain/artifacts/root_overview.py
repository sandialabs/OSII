import tomllib

from osii.domain.read.catalog import load_folders_catalog
from osii.domain.read.folder_synthesis import get_folder_synthesis_text
from osii.domain.storage.store import root_overview_path
import tomli_w


def read_folder_synth_toml(osii_root, folder_id: str) -> dict | None:
    path = (osii_root / "folders" / f"folder-{folder_id}.synth.toml").resolve()
    if not path.exists():
        return None
    return tomllib.loads(path.read_text(encoding="utf-8"))


def build_root_overview(osii_root):
    folders = load_folders_catalog(osii_root)

    payload = {
        "root": {
            "folder_count": len(folders),
        },
        "folders": [],
    }

    for entry in folders:
        relpath = (entry.get("path") or "").strip("/")
        if relpath == "":
            continue
        if "/" in relpath:
            continue  # only top-level children for root overview

        folder_id = entry.get("folder_id")
        if not folder_id:
            continue

        synth = read_folder_synth_toml(osii_root, folder_id)
        if not synth:
            continue

        payload["folders"].append(
            {
                "folder_id": folder_id,
                "path": relpath,
                "synthesis": synth.get("synthesis", {}).get("synthesis", ""),
                "kind": synth.get("synthesis", {}).get("kind", "folder"),
                "quality": synth.get("synthesis", {}).get("quality", "default"),
            }
        )

    path = root_overview_path(osii_root)
    path.write_text(tomli_w.dumps(payload), encoding="utf-8")
    return path