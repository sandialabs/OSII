"""Shared authoring over existing portable product histories and collections."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import uuid

from osii.domain.storage.authoring import (AuthoringConflict, ProductRef, ProductHistory,
    ProductRevision, CollectionRecord, product_history, validate_product_edit,
    collection_record, normalized_members, validate_identifier)


class SidecarProductAuthoring:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def _path(self, ref):
        from osii.domain.artifacts.products import product_path
        return product_path(self.root, ref.legacy_scope(), ref.filename, ref.family)

    def history(self, product: ProductRef) -> ProductHistory:
        from osii.domain.artifacts.products import read_product
        history = read_product(self._path(product))
        if not history["revisions"]:
            raise KeyError("Product not found")
        return product_history(product, history["current"], history["revisions"])

    def _change(self, ref, expected, *, data=None, revision=None, activate=False, actor=None):
        from osii.domain.artifacts.products import _load, _lock, _commit
        path = self._path(ref)
        with _lock(self.root):
            manifest = _load(path)
            if not manifest["revisions"]:
                raise KeyError("Product not found")
            if manifest["current"] != expected:
                raise AuthoringConflict("This product changed; reload its history before saving")
            current = next((r for r in manifest["revisions"] if r["id"] == expected), manifest["revisions"][-1])
            if revision is not None:
                source = next((r for r in manifest["revisions"] if r["id"] == revision), None)
                if source is None:
                    raise KeyError("Product revision not found")
                # Activation is a new editorial event, not a destructive pointer rewind.
                data = source["data"]
                provenance = {**source.get("provenance", {}), "activated_revision": revision}
            else:
                data = validate_product_edit(current["data"], data, max_characters=5_000_000)
                provenance = dict(current.get("provenance") or {})
            row = {"id": uuid.uuid4().hex, "parent": expected, "origin": "human",
                "created_at": datetime.now(UTC).isoformat(), "data": data, "provenance": provenance,
                "actor_id": actor, "grounding_needs_review": True,
                **({"restored_from": revision} if revision is not None else {})}
            manifest["revisions"].append(row)
            if activate:
                manifest["current"] = row["id"]
            _commit(path, manifest, write_compatibility=activate)
        return product_history(ref, manifest["current"], [row]).revisions[0]

    def save(self, product: ProductRef, data: dict, *, expected_revision: str | None,
             activate: bool = False, actor_id: str | None = None) -> ProductRevision:
        return self._change(product, expected_revision, data=data, activate=activate, actor=actor_id)

    def activate(self, product: ProductRef, revision_id: str, *, expected_revision: str | None,
                 actor_id: str | None = None) -> ProductRevision:
        return self._change(product, expected_revision, revision=revision_id, activate=True, actor=actor_id)


class SidecarCollectionStore:
    """Each command changes one canonical file; catalogs are only projections."""
    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def _raw(self, identity):
        from osii.domain.scopes.collections import _read_collection, _read_members
        validate_identifier(identity)
        path = self.root / "collections" / identity / "collection.toml"
        if not path.resolve().is_relative_to(self.root):
            raise ValueError("Collection reference escapes the library")
        record = _read_collection(path)
        if path.exists() and record is None:
            raise ValueError("Invalid collection descriptor; existing files were not changed")
        if record and record["id"] != identity:
            raise ValueError("Collection identity does not match its location")
        members = _read_members(self.root, identity) if record else []
        return record, members

    def get(self, collection_id: str) -> CollectionRecord | None:
        record, members = self._raw(collection_id)
        return collection_record(record, [row["file_id"] for row in members]) if record else None

    def list(self) -> tuple[CollectionRecord, ...]:
        directory = self.root / "collections"
        result = []
        for path in directory.iterdir() if directory.is_dir() else ():
            if path.is_dir() and not path.name.startswith("."):
                row = self.get(path.name)
                if row is not None:
                    result.append(row)
        return tuple(sorted(result, key=lambda row: (row.name, row.collection_id)))

    def create(self, name: str, *, description: str | None = None,
               collection_id: str | None = None) -> CollectionRecord:
        from osii.domain.artifacts.products import _lock
        from osii.domain.scopes.collections import _write_collection, utc_now_iso
        name = name.strip()
        if not name:
            raise ValueError("Collection name is required")
        identity = collection_id or "col-" + uuid.uuid4().hex[:12]
        validate_identifier(identity)
        with _lock(self.root):
            if self.get(identity) is not None:
                raise AuthoringConflict("Collection already exists")
            if any(row.name.casefold() == name.casefold() for row in self.list()):
                raise AuthoringConflict("Collection name already exists")
            now = utc_now_iso()
            _write_collection(self.root, {"id": identity, "name": name, "description": description,
                "kind": "manual", "created_utc": now, "updated_utc": now})
        from osii.domain.catalog_db import rebuild_catalog
        rebuild_catalog(self.root)
        return self.get(identity)

    def _change(self, identity, expected, *, name=None, description=None, members=None):
        from osii.domain.artifacts.products import _lock
        from osii.domain.scopes.collections import _write_collection, _write_members, utc_now_iso
        with _lock(self.root):
            record, previous_members = self._raw(identity)
            if record is None:
                raise KeyError("Collection not found")
            current = collection_record(record, [row["file_id"] for row in previous_members])
            if current.version != expected:
                raise AuthoringConflict("Collection changed; refresh before editing")
            if members is not None:
                ids = normalized_members(members)
                old = {row["file_id"]: row for row in previous_members}
                _write_members(self.root, identity, [old.get(fid) or {"file_id": fid, "created_utc": utc_now_iso()} for fid in ids])
            else:
                if name is not None:
                    if not name.strip():
                        raise ValueError("Collection name is required")
                    if any(row.collection_id != identity and row.name.casefold() == name.strip().casefold() for row in self.list()):
                        raise AuthoringConflict("Collection name already exists")
                    record["name"] = name.strip()
                if description is not None:
                    record["description"] = description
                record["updated_utc"] = utc_now_iso()
                _write_collection(self.root, record)
        # Failure to maintain a derived catalog cannot undo the canonical write.
        from osii.domain.catalog_db import rebuild_catalog
        rebuild_catalog(self.root)
        return self.get(identity)

    def update(self, collection_id: str, *, expected_version: str, name: str | None = None,
               description: str | None = None) -> CollectionRecord:
        return self._change(collection_id, expected_version, name=name, description=description)

    def replace_members(self, collection_id: str, member_ids, *, expected_version: str) -> CollectionRecord:
        return self._change(collection_id, expected_version, members=member_ids)
