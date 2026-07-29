from pathlib import Path
import tomllib


def folder_manifest_path(osii_store: Path, folder_id: str) -> Path:
    return (osii_store / "folders" / f"folder-{folder_id}.toml").resolve()


def folder_synth_path(osii_store: Path, folder_id: str) -> Path:
    return (osii_store / "folders" / f"folder-{folder_id}.synth.txt").resolve()


def get_folder_manifest(osii_store: Path, folder_id: str) -> dict | None:
    path = folder_manifest_path(osii_store, folder_id)
    if not path.exists():
        return None
    return tomllib.loads(path.read_text(encoding="utf-8"))


def get_folder_synth(osii_store: Path, folder_id: str) -> str | None:
    path = folder_synth_path(osii_store, folder_id)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")

def get_folder_synthesis(osii_store: Path, folder_id: str) -> str | None:
    # duplicate function for backwards compatibility
    path = folder_synth_path(osii_store, folder_id)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")