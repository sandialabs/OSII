from pathlib import Path

from osii.domain.read.manifest import (
    get_manifest_record_by_id,
    get_record_path,
    list_image_records,
)


def list_artifacts(osii_store: Path, file_id: str) -> list[dict]:
    return list_image_records(osii_store, file_id)


def get_artifact_record(osii_store: Path, file_id: str, artifact_id: str) -> dict | None:
    return get_manifest_record_by_id(osii_store, file_id, artifact_id)


def get_artifact_path(osii_store: Path, file_id: str, artifact_id: str) -> Path | None:
    record = get_artifact_record(osii_store, file_id, artifact_id)
    if record is None:
        return None
    return get_record_path(osii_store, file_id, record)