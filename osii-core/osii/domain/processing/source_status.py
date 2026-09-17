from __future__ import annotations

from pathlib import Path
import tomllib
import tomli_w

from osii.domain.storage.store import object_dir


def source_status_path(osii_root: Path, file_id: str) -> Path:
    obj_dir = object_dir(osii_root, file_id)
    obj_dir.mkdir(parents=True, exist_ok=True)
    return obj_dir / "source_status.toml"


def get_source_status(osii_root: Path, file_id: str) -> dict | None:
    path = source_status_path(osii_root, file_id)
    if not path.exists():
        return None
    return tomllib.loads(path.read_text(encoding="utf-8"))


def write_source_status(
    osii_root: Path,
    file_id: str,
    *,
    status: str,
    source_relpath: str | None = None,
) -> Path:
    path = source_status_path(osii_root, file_id)
    payload = {
        "source_status": {
            "status": status,
            "source_relpath": source_relpath or "",
        }
    }
    path.write_text(tomli_w.dumps(payload), encoding="utf-8")
    return path


def get_source_status_value(osii_root: Path, file_id: str) -> str:
    data = get_source_status(osii_root, file_id)
    if not data:
        return "active"
    return (data.get("source_status", {}).get("status") or "active").strip() or "active"