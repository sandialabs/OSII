from __future__ import annotations

from pathlib import Path
import json

from osii.domain.storage.store import object_dir

def artifact_staleness_path(osii_root: Path, file_id: str) -> Path:
    return object_dir(osii_root, file_id) / "artifact_staleness.json"


def get_artifact_staleness(osii_root: Path, file_id: str) -> dict | None:
    path = artifact_staleness_path(osii_root, file_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def mark_artifacts_stale(
    osii_root: Path,
    file_id: str,
    *,
    embeddings: bool = False,
    search_chunks: bool = False,
) -> dict:
    path = artifact_staleness_path(osii_root, file_id)
    payload = {
        "file_id": file_id,
        "stale": {
            "embeddings": embeddings,
            "search_chunks": search_chunks,
        },
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload