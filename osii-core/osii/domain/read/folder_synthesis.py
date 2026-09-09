from pathlib import Path
import tomllib

from osii.domain.storage.store import (
    folder_overview_path,
    folder_synth_path,
    folder_synth_toml_path,
)


def list_folder_syntheses(osii_store: Path, folder_id: str) -> list[dict]:
    txt_path = folder_synth_path(osii_store, folder_id)
    toml_path = folder_synth_toml_path(osii_store, folder_id)
    overview_path = folder_overview_path(osii_store, folder_id)

    if not txt_path.exists() and not toml_path.exists() and not overview_path.exists():
        return []

    return [
        {
            "folder_id": folder_id,
            "name": "current",
            "text_path": str(txt_path) if txt_path.exists() else None,
            "toml_path": str(toml_path) if toml_path.exists() else None,
            "overview_path": str(overview_path) if overview_path.exists() else None,
            "scope": "folder",
        }
    ]


def get_folder_synthesis_text(osii_store: Path, folder_id: str) -> str | None:
    path = folder_synth_path(osii_store, folder_id)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def get_folder_synthesis_toml(osii_store: Path, folder_id: str) -> dict | None:
    path = folder_synth_toml_path(osii_store, folder_id)
    if not path.exists():
        return None
    return tomllib.loads(path.read_text(encoding="utf-8"))


def get_folder_overview_toml(osii_store: Path, folder_id: str) -> dict | None:
    path = folder_overview_path(osii_store, folder_id)
    if not path.exists():
        return None
    return tomllib.loads(path.read_text(encoding="utf-8"))