from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import tomllib
import uuid
from datetime import UTC, datetime
from pathlib import Path

from osii.domain.artifacts.artifact_staleness import mark_artifacts_stale
from osii.domain.storage.atomic import atomic_write_text
from osii.domain.storage.ids import compute_file_id
from osii.domain.storage.store import object_dir

EXTRACTION_FILES = ("text.txt", "manifest.jsonl", "provenance.toml")


def extractions_dir(osii_root: Path, file_id: str) -> Path:
    path = object_dir(osii_root, file_id) / "extractions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def extraction_index_path(osii_root: Path, file_id: str) -> Path:
    return extractions_dir(osii_root, file_id) / "index.json"


def _load_index(osii_root: Path, file_id: str) -> dict:
    path = extraction_index_path(osii_root, file_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    variants = payload.get("variants")
    return {
        "primary_id": payload.get("primary_id"),
        "variants": variants if isinstance(variants, list) else [],
    }


def _write_index(osii_root: Path, file_id: str, payload: dict) -> Path:
    return atomic_write_text(
        extraction_index_path(osii_root, file_id),
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
    )


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9.-]+", "-", value.lower()).strip("-") or "extractor"


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _provenance_record(bundle: Path) -> tuple[str, str, str]:
    try:
        payload = tomllib.loads((bundle / "provenance.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        payload = {}
    extractor = payload.get("extractor") or {}
    provenance = payload.get("provenance") or {}
    return (
        str(extractor.get("name") or "unknown"),
        str(extractor.get("version") or "unknown"),
        str(provenance.get("status") or "unknown"),
    )


def _copy_extraction_bundle(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for name in EXTRACTION_FILES:
        candidate = source / name
        if candidate.is_file():
            shutil.copy2(candidate, destination / name)
    source_artifacts = source / "artifacts"
    if source_artifacts.is_dir():
        shutil.copytree(source_artifacts, destination / "artifacts")
    else:
        (destination / "artifacts").mkdir()


def _variant_record(bundle: Path, variant_id: str, *, created_utc: str | None = None) -> dict:
    extractor_name, extractor_version, status = _provenance_record(bundle)
    return {
        "id": variant_id,
        "created_utc": created_utc or datetime.now(UTC).isoformat(),
        "extractor": {
            "name": extractor_name,
            "version": extractor_version,
        },
        "status": status,
        "text_sha256": _sha256(bundle / "text.txt"),
        "text_chars": len((bundle / "text.txt").read_text(encoding="utf-8")) if (bundle / "text.txt").is_file() else 0,
        "manifest_records": sum(1 for line in (bundle / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()) if (bundle / "manifest.jsonl").is_file() else 0,
    }


def _archive_legacy_primary(osii_root: Path, file_id: str) -> dict | None:
    obj = object_dir(osii_root, file_id)
    index = _load_index(osii_root, file_id)
    if index["variants"] or not (obj / "text.txt").is_file():
        return None
    extractor_name, _, _ = _provenance_record(obj)
    variant_id = f"legacy-{_slug(extractor_name)}-{uuid.uuid4().hex[:8]}"
    destination = extractions_dir(osii_root, file_id) / variant_id
    _copy_extraction_bundle(obj, destination)
    record = _variant_record(destination, variant_id)
    index = {"primary_id": variant_id, "variants": [record]}
    _write_index(osii_root, file_id, index)
    return record


def list_extraction_variants(osii_root: Path, file_id: str) -> dict | None:
    obj = object_dir(osii_root, file_id)
    if not obj.is_dir():
        return None
    _archive_legacy_primary(osii_root, file_id)
    index = _load_index(osii_root, file_id)
    primary_id = index.get("primary_id")
    variants = []
    for record in index["variants"]:
        variant_id = str(record.get("id") or "")
        if not variant_id:
            continue
        variants.append({
            **record,
            "primary": variant_id == primary_id,
            "text_path": f"objects/{file_id}/extractions/{variant_id}/text.txt",
            "manifest_path": f"objects/{file_id}/extractions/{variant_id}/manifest.jsonl",
            "provenance_path": f"objects/{file_id}/extractions/{variant_id}/provenance.toml",
        })
    return {"file_id": file_id, "primary_id": primary_id, "variants": variants}


def list_extraction_artifacts(
    osii_root: Path,
    file_id: str,
    variant_id: str,
    *,
    maximum_json_bytes: int = 5 * 1024 * 1024,
) -> list[dict]:
    """Return safe preview data for non-text products from one extraction."""
    state = list_extraction_variants(osii_root, file_id)
    if state is None:
        raise FileNotFoundError(f"Object not found: {file_id}")
    if not any(item.get("id") == variant_id for item in state["variants"]):
        raise FileNotFoundError(f"Extraction variant not found: {variant_id}")

    bundle = (extractions_dir(osii_root, file_id) / variant_id).resolve()
    try:
        bundle.relative_to(extractions_dir(osii_root, file_id).resolve())
    except ValueError as exc:
        raise FileNotFoundError(f"Extraction variant not found: {variant_id}") from exc

    manifest_path = bundle / "manifest.jsonl"
    if not manifest_path.is_file():
        return []

    artifacts: list[dict] = []
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("kind") == "text" or not record.get("path"):
            continue
        artifact_path = (bundle / str(record["path"])).resolve()
        try:
            artifact_path.relative_to(bundle)
        except ValueError:
            continue
        item = {
            "id": str(record.get("id") or artifact_path.name),
            "kind": str(record.get("kind") or "artifact"),
            "media_type": str(record.get("type") or "application/octet-stream"),
            "source_origin": record.get("source_origin") or {},
            "filename": artifact_path.name,
            "size_bytes": artifact_path.stat().st_size if artifact_path.is_file() else None,
            "data": None,
        }
        if (
            artifact_path.is_file()
            and item["media_type"] == "application/json"
            and artifact_path.stat().st_size <= maximum_json_bytes
        ):
            try:
                item["data"] = json.loads(artifact_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        artifacts.append(item)
    return artifacts


def primary_extraction_dir(osii_root: Path, file_id: str) -> Path | None:
    state = list_extraction_variants(osii_root, file_id)
    if not state or not state.get("primary_id"):
        return None
    path = extractions_dir(osii_root, file_id) / str(state["primary_id"])
    return path if path.is_dir() else None


def promote_extraction_variant(osii_root: Path, file_id: str, variant_id: str) -> dict:
    _archive_legacy_primary(osii_root, file_id)
    index = _load_index(osii_root, file_id)
    if not any(item.get("id") == variant_id for item in index["variants"]):
        raise FileNotFoundError(f"Extraction variant not found: {variant_id}")
    source = extractions_dir(osii_root, file_id) / variant_id
    if not (source / "text.txt").is_file():
        raise RuntimeError(f"Extraction variant has no text: {variant_id}")

    previous = index.get("primary_id")
    obj = object_dir(osii_root, file_id)
    for name in EXTRACTION_FILES:
        candidate = source / name
        target = obj / name
        if candidate.is_file():
            atomic_write_text(target, candidate.read_text(encoding="utf-8"))
        else:
            target.unlink(missing_ok=True)

    staged_artifacts = obj / f".artifacts-{uuid.uuid4().hex}"
    shutil.copytree(source / "artifacts", staged_artifacts)
    current_artifacts = obj / "artifacts"
    if current_artifacts.exists():
        shutil.rmtree(current_artifacts)
    staged_artifacts.replace(current_artifacts)

    index["primary_id"] = variant_id
    _write_index(osii_root, file_id, index)
    if previous and previous != variant_id:
        mark_artifacts_stale(
            osii_root,
            file_id,
            embeddings=True,
            search_chunks=True,
            syntheses=True,
            enrichments=True,
        )
    return list_extraction_variants(osii_root, file_id) or {}


def extract_document_variant(
    *,
    extractor_name: str,
    source_path: Path,
    data_volume_root: Path,
    osii_root: Path,
    expert_context: str | None = None,
    extractor_config: dict | None = None,
    make_primary: bool = True,
    dispatcher=None,
) -> dict:
    """Run an extractor in isolation, then atomically register its output."""
    if dispatcher is None:
        from osii.extraction.dispatcher import dispatch_extract
        dispatcher = dispatch_extract

    file_id = compute_file_id(source_path)
    _archive_legacy_primary(osii_root, file_id)
    with tempfile.TemporaryDirectory(prefix="osii-extraction-") as temporary:
        temporary_root = Path(temporary) / ".osii"
        result = dispatcher(
            extractor_name=extractor_name,
            source_path=source_path,
            data_volume_root=data_volume_root,
            osii_store=temporary_root,
            expert_context=expert_context,
            extractor_config=extractor_config or {},
        )
        temporary_object = object_dir(temporary_root, file_id)
        actual_object = object_dir(osii_root, file_id)
        actual_object.mkdir(parents=True, exist_ok=True)
        temporary_meta = temporary_object / "meta.toml"
        if temporary_meta.is_file():
            atomic_write_text(actual_object / "meta.toml", temporary_meta.read_text(encoding="utf-8"))

        extractor_actual, _, _ = _provenance_record(temporary_object)
        variant_id = f"{_slug(extractor_actual)}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        extraction_root = extractions_dir(osii_root, file_id)
        staged = extraction_root / f".{variant_id}.tmp"
        destination = extraction_root / variant_id
        _copy_extraction_bundle(temporary_object, staged)
        staged.replace(destination)

    index = _load_index(osii_root, file_id)
    record = _variant_record(destination, variant_id)
    index["variants"].append(record)
    _write_index(osii_root, file_id, index)
    if make_primary or not index.get("primary_id"):
        promote_extraction_variant(osii_root, file_id, variant_id)
    return {
        **result,
        "variant_id": variant_id,
        "made_primary": bool(make_primary or not index.get("primary_id")),
        "extraction": record,
    }
