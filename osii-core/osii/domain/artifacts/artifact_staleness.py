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
    syntheses: bool = False,
    enrichments: bool = False,
) -> dict:
    path = artifact_staleness_path(osii_root, file_id)
    existing = get_artifact_staleness(osii_root, file_id) or {}
    current = existing.get("stale") if isinstance(existing.get("stale"), dict) else {}
    payload = {
        "file_id": file_id,
        "stale": {
            "embeddings": bool(current.get("embeddings") or embeddings),
            "search_chunks": bool(current.get("search_chunks") or search_chunks),
            "syntheses": bool(current.get("syntheses") or syntheses),
            "enrichments": bool(current.get("enrichments") or enrichments),
        },
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def clear_artifacts_stale(osii_root: Path, file_id: str, *names: str) -> dict:
    current = get_artifact_staleness(osii_root, file_id) or {
        "file_id": file_id,
        "stale": {},
    }
    stale = current.get("stale") if isinstance(current.get("stale"), dict) else {}
    for name in names:
        stale[name] = False
    current["stale"] = stale
    artifact_staleness_path(osii_root, file_id).write_text(
        json.dumps(current, indent=2),
        encoding="utf-8",
    )
    return current
