from __future__ import annotations

from pathlib import Path
import tomllib
import tomli_w
import uuid


def folder_ids_registry_path(osii_root: Path) -> Path:
    path = (osii_root / "folders" / "folder_ids.toml").resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _normalize_relpath(relpath: str) -> str:
    return str(relpath or "").strip().replace("\\", "/").strip("/")


def load_folder_id_registry(osii_root: Path) -> dict[str, str]:
    path = folder_ids_registry_path(osii_root)
    if not path.exists():
        return {}

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    raw_entries = data.get("folder_ids", {})
    result = {}

    for relpath, folder_id in raw_entries.items():
        norm = _normalize_relpath(relpath)
        if folder_id:
            result[norm] = str(folder_id)

    return result


def save_folder_id_registry(osii_root: Path, mapping: dict[str, str]) -> Path:
    path = folder_ids_registry_path(osii_root)

    normalized = {
        _normalize_relpath(relpath): folder_id
        for relpath, folder_id in mapping.items()
    }

    path.write_text(
        tomli_w.dumps({"folder_ids": normalized}),
        encoding="utf-8",
    )
    return path


def get_or_create_folder_id_for_relpath(
    osii_root: Path,
    relpath: str,
    *,
    registry: dict[str, str] | None = None,
) -> tuple[str, dict[str, str]]:
    mapping = dict(registry or {})
    norm = _normalize_relpath(relpath)

    if norm in mapping:
        return mapping[norm], mapping

    mapping[norm] = str(uuid.uuid4())
    return mapping[norm], mapping