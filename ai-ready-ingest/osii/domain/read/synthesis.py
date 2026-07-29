from pathlib import Path
import tomllib

from osii.domain.storage.store import object_dir, object_synth_path, object_synth_toml_path


def get_synth_text(osii_store: Path, file_id: str) -> str | None:
    path = object_synth_path(osii_store, file_id)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def get_synth_toml(osii_store: Path, file_id: str) -> dict | None:
    path = object_synth_toml_path(osii_store, file_id)
    if not path.exists():
        return None
    return tomllib.loads(path.read_text(encoding="utf-8"))


def list_syntheses(osii_store: Path, file_id: str) -> list[dict]:
    txt_path = object_synth_path(osii_store, file_id)
    toml_path = object_synth_toml_path(osii_store, file_id)

    if not txt_path.exists() and not toml_path.exists():
        return []

    return [
        {
            "name": "current",
            "text_path": str(txt_path) if txt_path.exists() else None,
            "toml_path": str(toml_path) if toml_path.exists() else None,
            "scope": "object",
        }
    ]