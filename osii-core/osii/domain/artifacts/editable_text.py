from datetime import datetime, UTC
from pathlib import Path

from osii.domain.storage.store import object_dir


def editable_text_path(osii_root: Path, file_id: str) -> Path:
    return (object_dir(osii_root, file_id) / "editable_text.txt").resolve()


def get_editable_text(osii_root: Path, file_id: str) -> dict | None:
    obj_dir = object_dir(osii_root, file_id)
    if not obj_dir.exists():
        return None

    path = editable_text_path(osii_root, file_id)
    if not path.exists():
        return {
            "file_id": file_id,
            "text": None,
            "path": f"objects/{file_id}/editable_text.txt",
            "exists": False,
            "source_kind": "editable",
        }

    return {
        "file_id": file_id,
        "text": path.read_text(encoding="utf-8"),
        "path": f"objects/{file_id}/editable_text.txt",
        "exists": True,
        "source_kind": "editable",
    }


def put_editable_text(osii_root: Path, file_id: str, text: str) -> dict | None:
    obj_dir = object_dir(osii_root, file_id)
    if not obj_dir.exists():
        return None

    path = editable_text_path(osii_root, file_id)
    path.write_text(text, encoding="utf-8")

    return {
        "ok": True,
        "file_id": file_id,
        "path": f"objects/{file_id}/editable_text.txt",
        "updated_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


def delete_editable_text(osii_root: Path, file_id: str) -> dict | None:
    obj_dir = object_dir(osii_root, file_id)
    if not obj_dir.exists():
        return None

    path = editable_text_path(osii_root, file_id)
    if path.exists():
        path.unlink()
        removed = True
    else:
        removed = False

    return {
        "ok": True,
        "file_id": file_id,
        "removed": removed,
    }