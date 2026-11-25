from __future__ import annotations

from pathlib import Path
import json

from osii.domain.storage.store import object_dir
from osii.domain.storage.atomic import atomic_write_text

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
    syntheses: bool = False,
    enrichments: bool = False,
) -> dict:
    return _update(osii_root, file_id, {
        name: True for name, stale in {
            "embeddings": embeddings, "search_chunks": search_chunks, "syntheses": syntheses,
            "enrichments": enrichments, "document_metadata": enrichments,
        }.items() if stale
    })


def clear_artifacts_stale(osii_root: Path, file_id: str, *names: str) -> dict:
    return _update(osii_root, file_id, dict.fromkeys(names, False))


def _update(osii_root: Path, file_id: str, changes: dict) -> dict:
    from osii.domain.storage.sidecar_commits import _lock

    with _lock(osii_root, "artifact-staleness"):
        current = get_artifact_staleness(osii_root, file_id) or {}
        stale = current.get("stale")
        stale = stale if isinstance(stale, dict) else {}
        payload = {"file_id": file_id, "stale": {
            "embeddings": False, "search_chunks": False, "syntheses": False, "enrichments": False,
            "document_metadata": stale.get("enrichments", False), **stale, **changes,
        }}
        atomic_write_text(artifact_staleness_path(osii_root, file_id), json.dumps(payload, indent=2))
        return payload
