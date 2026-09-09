from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import zipfile

from osii.domain.catalog_db import rebuild_catalog
from osii.domain.governance import get_governance, merge_governance
from osii.domain.scopes.collections import (
    add_documents_to_collection,
    create_collection,
    get_collection,
    list_collection_documents,
    list_collections,
)


PACKAGE_FORMAT = "osii-sidecar-package"
PACKAGE_VERSION = 1
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_FILE_COUNT = 20_000


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_member(name: str) -> str:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or ".." in path.parts or normalized.startswith("/"):
        raise ValueError(f"Unsafe archive path: {name}")
    return path.as_posix()


def _directory_files(directory: Path, prefix: str) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    if directory.exists():
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                relpath = f"{prefix}/{path.relative_to(directory).as_posix()}"
                files[_safe_member(relpath)] = path.read_bytes()
    return files


def create_collection_package(osii_root: Path, collection_id: str) -> bytes:
    collection = get_collection(osii_root, collection_id)
    if collection is None:
        raise ValueError("unknown collection_id")
    file_ids = list_collection_documents(osii_root, collection_id)
    files = _directory_files(osii_root / "collections" / collection_id, f"collections/{collection_id}")
    for file_id in file_ids:
        files.update(_directory_files(osii_root / "objects" / file_id, f"objects/{file_id}"))

    manifest = {
        "format": PACKAGE_FORMAT,
        "version": PACKAGE_VERSION,
        "created_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "package_type": "collection",
        "source_files_included": False,
        "collection": {"id": collection_id, "name": collection["name"]},
        "objects": [
            {"file_id": file_id, "governance": get_governance(osii_root, file_id)}
            for file_id in file_ids
        ],
        "files": [
            {"path": path, "size_bytes": len(content), "sha256": _sha256_bytes(content)}
            for path, content in sorted(files.items())
        ],
    }
    output = tempfile.SpooledTemporaryFile(max_size=16 * 1024 * 1024)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, content in sorted(files.items()):
            archive.writestr(path, content)
        archive.writestr("osii-package.json", json.dumps(manifest, indent=2, sort_keys=True))
    output.seek(0)
    return output.read()


def _load_and_validate(archive_bytes: bytes) -> tuple[dict, dict[str, bytes]]:
    if len(archive_bytes) > MAX_ARCHIVE_BYTES:
        raise ValueError("Package is larger than the 512 MB safety limit.")
    try:
        # Re-open from an in-memory stream without extracting untrusted names.
        from io import BytesIO

        archive = zipfile.ZipFile(BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("The uploaded file is not a valid ZIP package.") from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_FILE_COUNT:
            raise ValueError("Package contains too many files.")
        if sum(info.file_size for info in infos) > MAX_ARCHIVE_BYTES:
            raise ValueError("Expanded package is larger than the 512 MB safety limit.")
        names = [_safe_member(info.filename) for info in infos if not info.is_dir()]
        if len(names) != len(set(names)):
            raise ValueError("Package contains duplicate paths.")
        if "osii-package.json" not in names:
            raise ValueError("Package manifest osii-package.json is missing.")
        manifest = json.loads(archive.read("osii-package.json"))
        if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
            raise ValueError("Package manifest has an invalid structure.")
        if manifest.get("format") != PACKAGE_FORMAT or manifest.get("version") != PACKAGE_VERSION:
            raise ValueError("Unsupported OSII package format or version.")
        try:
            expected = {str(item["path"]): item for item in manifest["files"]}
        except (KeyError, TypeError) as exc:
            raise ValueError("Package file manifest has an invalid structure.") from exc
        if len(expected) != len(manifest["files"]):
            raise ValueError("Package manifest contains duplicate file paths.")
        actual_names = set(names) - {"osii-package.json"}
        if actual_names != set(expected):
            raise ValueError("Package contents do not match its manifest.")
        files: dict[str, bytes] = {}
        total = 0
        for name in sorted(actual_names):
            content = archive.read(name)
            total += len(content)
            if total > MAX_ARCHIVE_BYTES:
                raise ValueError("Expanded package is larger than the 512 MB safety limit.")
            record = expected[name]
            if len(content) != int(record.get("size_bytes", -1)) or _sha256_bytes(content) != record.get("sha256"):
                raise ValueError(f"Package checksum failed for {name}.")
            files[name] = content
    return manifest, files


def _unique_collection_name(osii_root: Path, preferred: str) -> str:
    existing = {item["name"].casefold() for item in list_collections(osii_root)}
    if preferred.casefold() not in existing:
        return preferred
    counter = 1
    while True:
        suffix = " (imported)" if counter == 1 else f" (imported {counter})"
        candidate = f"{preferred}{suffix}"
        if candidate.casefold() not in existing:
            return candidate
        counter += 1


def _write_files(directory: Path, files: dict[str, bytes], prefix: str) -> None:
    prefix_with_slash = f"{prefix}/"
    for archive_path, content in files.items():
        if not archive_path.startswith(prefix_with_slash):
            continue
        relpath = archive_path[len(prefix_with_slash) :]
        target = directory / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def import_package(osii_root: Path, archive_bytes: bytes) -> dict:
    manifest, files = _load_and_validate(archive_bytes)
    if manifest.get("package_type") != "collection":
        raise ValueError("Only collection sidecar packages are supported in version 1.")
    osii_root = osii_root.resolve()
    object_records = manifest.get("objects")
    incoming_collection = manifest.get("collection")
    if not isinstance(object_records, list) or not isinstance(incoming_collection, dict):
        raise ValueError("Package objects or collection manifest is invalid.")
    incoming_id = str(incoming_collection.get("id") or "")
    incoming_name = str(incoming_collection.get("name") or "").strip()
    if (
        not incoming_id
        or incoming_id in {".", ".."}
        or "/" in incoming_id
        or "\\" in incoming_id
        or not incoming_name
    ):
        raise ValueError("Package contains an invalid collection descriptor.")
    collection_prefix = f"collections/{incoming_id}"
    if f"{collection_prefix}/collection.toml" not in files or f"{collection_prefix}/members.jsonl" not in files:
        raise ValueError("Package collection sidecar is incomplete.")

    validated_file_ids: list[str] = []
    for object_record in object_records:
        if not isinstance(object_record, dict):
            raise ValueError("Package contains an invalid object descriptor.")
        file_id = str(object_record.get("file_id") or "")
        if not file_id or file_id in {".", ".."} or "/" in file_id or "\\" in file_id:
            raise ValueError("Package contains an invalid object identifier.")
        object_prefix = f"objects/{file_id}"
        if f"{object_prefix}/meta.toml" not in files:
            raise ValueError(f"Object bundle is incomplete for {file_id}.")
        validated_file_ids.append(file_id)
    if len(validated_file_ids) != len(set(validated_file_ids)):
        raise ValueError("Package contains duplicate object descriptors.")
    allowed_prefixes = [f"collections/{incoming_id}/", *(f"objects/{file_id}/" for file_id in validated_file_ids)]
    if any(not any(path.startswith(prefix) for prefix in allowed_prefixes) for path in files):
        raise ValueError("Package contains files outside its declared collection and objects.")

    imported: list[str] = []
    duplicates: list[str] = []
    merged_labels: list[str] = []

    with tempfile.TemporaryDirectory(prefix="osii-import-") as temporary_name:
        staging = Path(temporary_name)
        for object_record in object_records:
            file_id = str(object_record.get("file_id") or "")
            object_prefix = f"objects/{file_id}"
            target = osii_root / "objects" / file_id
            if target.exists():
                duplicates.append(file_id)
                incoming = object_record.get("governance") or {}
                if incoming and merge_governance(osii_root, file_id, incoming):
                    merged_labels.append(file_id)
                continue
            staged = staging / file_id
            _write_files(staged, files, object_prefix)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged, target)
            imported.append(file_id)

        member_path = f"{collection_prefix}/members.jsonl"
        member_ids: list[str] = []
        for line in files.get(member_path, b"").decode("utf-8", errors="replace").splitlines():
            try:
                file_id = str(json.loads(line).get("file_id") or "")
            except json.JSONDecodeError:
                continue
            if file_id and (osii_root / "objects" / file_id).is_dir():
                member_ids.append(file_id)

        existing_collection = get_collection(osii_root, incoming_id) if incoming_id else None
        if existing_collection and existing_collection["name"].casefold() == incoming_name.casefold():
            target_collection_id = incoming_id
        else:
            created = create_collection(osii_root, name=_unique_collection_name(osii_root, incoming_name))
            target_collection_id = created["id"]
        add_documents_to_collection(osii_root, target_collection_id, member_ids)

        # Preserve imported collection knowledge products without replacing local products.
        target_collection_dir = osii_root / "collections" / target_collection_id
        for archive_path, content in files.items():
            if not archive_path.startswith(f"{collection_prefix}/"):
                continue
            relpath = archive_path[len(collection_prefix) + 1 :]
            if relpath in {"collection.toml", "members.jsonl"}:
                continue
            target = target_collection_dir / relpath
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)

    # Every corpus-wide index is derived. Removing it prevents stale results or mixed vector spaces.
    shutil.rmtree(osii_root / "embeddings", ignore_errors=True)
    (osii_root / "embeddings").mkdir(parents=True, exist_ok=True)
    rebuild_catalog(osii_root)
    return {
        "ok": True,
        "collection_id": target_collection_id,
        "imported_file_ids": imported,
        "duplicate_file_ids": duplicates,
        "governance_merged_file_ids": merged_labels,
        "indexes_rebuild_required": True,
        "source_files_included": False,
    }
