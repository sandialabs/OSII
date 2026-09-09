from pathlib import Path
import tomllib

from osii.domain.storage.store import root_overview_path, root_synth_path, root_toml_path


def get_root_descriptor(osii_store: Path) -> dict | None:
    path = root_toml_path(osii_store)
    if not path.exists():
        return None
    return tomllib.loads(path.read_text(encoding="utf-8"))


def get_root_synth_text(osii_store: Path) -> str | None:
    path = root_synth_path(osii_store)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def get_root_overview_toml(osii_store: Path) -> dict | None:
    path = root_overview_path(osii_store)
    if not path.exists():
        return None
    return tomllib.loads(path.read_text(encoding="utf-8"))