from __future__ import annotations

from pathlib import Path
import json

from osii.domain.storage.store import (
    collection_enrichments_dir,
    folder_enrichments_dir,
    object_enrichments_dir,
    root_enrichments_dir,
)


def _variant_basename(kind: str, method: str) -> str:
    kind = (kind or "").strip()
    method = (method or "").strip()

    if not kind:
        raise ValueError("kind is required")
    if not method:
        raise ValueError("method is required")

    return f"{kind.replace(' ', '_')}--{method.replace(' ', '_')}"


def _scope_enrichment_dir(osii_root: Path, scope: dict) -> tuple[str, Path, str]:
    scope_type = (scope.get("scope_type") or scope.get("type") or "").strip().lower()

    if scope_type == "object":
        file_id = (scope.get("file_id") or "").strip()
        return "object", object_enrichments_dir(osii_root, file_id), file_id

    if scope_type == "folder":
        folder_id = (scope.get("folder_id") or "").strip()
        return "folder", folder_enrichments_dir(osii_root, folder_id), folder_id

    if scope_type == "collection":
        collection_id = (scope.get("collection_id") or "").strip()
        return "collection", collection_enrichments_dir(osii_root, collection_id), collection_id

    if scope_type == "root":
        return "root", root_enrichments_dir(osii_root), "root"

    raise ValueError(f"Unsupported scope type for enrichment artifacts: {scope_type}")


def create_enrichment_output_dir(
    osii_root: Path,
    scope: dict,
    *,
    kind: str,
    method: str,
) -> dict:
    scope_type, base_dir, scope_id = _scope_enrichment_dir(osii_root, scope)
    dirname = _variant_basename(kind, method)
    out_dir = base_dir / dirname
    out_dir.mkdir(parents=True, exist_ok=True)

    if scope_type == "object":
        relpath = f"objects/{scope_id}/enrichments/{dirname}"
    elif scope_type == "folder":
        relpath = f"folders/folder-{scope_id}.enrichments/{dirname}"
    elif scope_type == "collection":
        relpath = f"collections/{scope_id}/enrichments/{dirname}"
    else:
        relpath = f"enrichments/{dirname}"

    return {
        "scope_type": scope_type,
        "scope_id": scope_id,
        "kind": kind,
        "method": method,
        "dir_path": out_dir,
        "relpath": relpath,
    }


def write_object_enrichment_variant(
    osii_root: Path,
    file_id: str,
    *,
    kind: str,
    method: str,
    payload: dict | list,
    metadata: dict | None = None,
) -> dict:
    base = _variant_basename(kind, method)
    out_dir = object_enrichments_dir(osii_root, file_id)

    data_path = out_dir / f"{base}.json"
    meta_path = out_dir / f"{base}.meta.json"

    data_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    meta_path.write_text(json.dumps(metadata or {}, indent=2), encoding="utf-8")

    return {
        "scope_type": "object",
        "file_id": file_id,
        "kind": kind,
        "method": method,
        "data_path": f"objects/{file_id}/enrichments/{data_path.name}",
        "metadata_path": f"objects/{file_id}/enrichments/{meta_path.name}",
    }


def write_folder_enrichment_variant(
    osii_root: Path,
    folder_id: str,
    *,
    kind: str,
    method: str,
    payload: dict | list,
    metadata: dict | None = None,
) -> dict:
    base = _variant_basename(kind, method)
    out_dir = folder_enrichments_dir(osii_root, folder_id)

    data_path = out_dir / f"{base}.json"
    meta_path = out_dir / f"{base}.meta.json"

    data_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    meta_path.write_text(json.dumps(metadata or {}, indent=2), encoding="utf-8")

    return {
        "scope_type": "folder",
        "folder_id": folder_id,
        "kind": kind,
        "method": method,
        "data_path": f"folders/folder-{folder_id}.enrichments/{data_path.name}",
        "metadata_path": f"folders/folder-{folder_id}.enrichments/{meta_path.name}",
    }


def write_collection_enrichment_variant(
    osii_root: Path,
    collection_id: str,
    *,
    kind: str,
    method: str,
    payload: dict | list,
    metadata: dict | None = None,
) -> dict:
    base = _variant_basename(kind, method)
    out_dir = collection_enrichments_dir(osii_root, collection_id)

    data_path = out_dir / f"{base}.json"
    meta_path = out_dir / f"{base}.meta.json"

    data_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    meta_path.write_text(json.dumps(metadata or {}, indent=2), encoding="utf-8")

    return {
        "scope_type": "collection",
        "collection_id": collection_id,
        "kind": kind,
        "method": method,
        "data_path": f"collections/{collection_id}/enrichments/{data_path.name}",
        "metadata_path": f"collections/{collection_id}/enrichments/{meta_path.name}",
    }


def write_root_enrichment_variant(
    osii_root: Path,
    *,
    kind: str,
    method: str,
    payload: dict | list,
    metadata: dict | None = None,
) -> dict:
    base = _variant_basename(kind, method)
    out_dir = root_enrichments_dir(osii_root)

    data_path = out_dir / f"{base}.json"
    meta_path = out_dir / f"{base}.meta.json"

    data_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    meta_path.write_text(json.dumps(metadata or {}, indent=2), encoding="utf-8")

    return {
        "scope_type": "root",
        "scope_id": "root",
        "kind": kind,
        "method": method,
        "data_path": f"enrichments/{data_path.name}",
        "metadata_path": f"enrichments/{meta_path.name}",
    }


def write_scope_enrichment_variant(
    osii_root: Path,
    scope: dict,
    *,
    kind: str,
    method: str,
    payload: dict | list,
    metadata: dict | None = None,
) -> dict:
    scope_type, _, scope_id = _scope_enrichment_dir(osii_root, scope)
    if scope_type == "object":
        return write_object_enrichment_variant(
            osii_root, scope_id, kind=kind, method=method,
            payload=payload, metadata=metadata,
        )
    if scope_type == "folder":
        return write_folder_enrichment_variant(
            osii_root, scope_id, kind=kind, method=method,
            payload=payload, metadata=metadata,
        )
    if scope_type == "collection":
        return write_collection_enrichment_variant(
            osii_root, scope_id, kind=kind, method=method,
            payload=payload, metadata=metadata,
        )
    return write_root_enrichment_variant(
        osii_root, kind=kind, method=method,
        payload=payload, metadata=metadata,
    )
