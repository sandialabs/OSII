import hashlib
import json
from datetime import datetime, UTC
from pathlib import Path

from .pathing import display_rel


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def save_manifest(
    resolved_files: list[Path],
    queue_items: list[dict],
    include_subfolders: bool,
    include_patterns: list[str],
    exclude_patterns: list[str],
    context: str,
    data_volume_root: Path,
    osii_root: Path,
    shared_root: Path,
    upload_root: Path,
) -> Path:
    manifests_dir = osii_root / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC)
    manifest_path = manifests_dir / f"intake-manifest-{timestamp.strftime('%Y%m%dT%H%M%SZ')}.json"

    files_payload = []
    for p in resolved_files:
        try:
            size = p.stat().st_size
        except Exception:
            size = None

        try:
            file_hash = sha256_file(p)
        except Exception:
            file_hash = None

        files_payload.append(
            {
                "path": str(p),
                "display": display_rel(p, shared_root, upload_root),
                "size": size,
                "sha256": file_hash,
            }
        )

    payload = {
        "timestamp_utc": timestamp.isoformat(),
        "data_volume_root": str(data_volume_root),
        "selection_queue": queue_items,
        "include_subfolders": include_subfolders,
        "include_patterns": include_patterns,
        "exclude_patterns": exclude_patterns,
        "context": context,
        "files": files_payload,
    }

    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return manifest_path