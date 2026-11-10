"""Authoring and collection adapters over the existing hosted PostgreSQL schema.

No migrations, sidecar fallback, accounts, or application startup are hidden here.
The hosted composition authorizes mutations before invoking these adapters.
"""
from __future__ import annotations

from datetime import UTC, datetime
import json
import uuid

from osii.domain.storage.authoring import (AuthoringConflict, ProductRef, ProductHistory,
    ProductRevision, CollectionRecord, product_history, validate_product_edit,
    collection_record, normalized_members, validate_identifier)


def _sql(conn, query, **values):
    from sqlalchemy import text
    return conn.execute(text(query), values)


class PostgresProductAuthoring:
    def __init__(self, engine, *, actor_id: str | None = None):
        if engine.dialect.name != "postgresql":
            raise ValueError("PostgreSQL is required")
        self.engine, self.actor_id = engine, actor_id

    def _product(self, conn, ref, *, lock=False):
        if ref.scope.kind == "collection":
            visible = _sql(conn, """SELECT id FROM collections WHERE id=:id
                AND (visibility='shared' OR owner_id=:actor) FOR SHARE""", id=ref.scope.identifier, actor=self.actor_id).first()
            if visible is None:
                raise KeyError("Collection not found")
        row = _sql(conn, """SELECT * FROM scope_products WHERE scope_type=:kind AND scope_id=:scope
            AND filename=:name AND family=:family""" + (" FOR UPDATE" if lock else ""),
            kind=ref.scope.kind, scope=ref.scope.identifier or "root", name=ref.filename, family=ref.family).mappings().first()
        if row is None:
            raise KeyError("Product not found")
        return row

    def history(self, product: ProductRef) -> ProductHistory:
        with self.engine.begin() as conn:
            record = self._product(conn, product)
            rows = [dict(row) for row in _sql(conn, "SELECT * FROM scope_revisions WHERE product_id=:id ORDER BY created_at,id",
                id=record["id"]).mappings()]
            return product_history(product, record["current_revision"], rows)

    def _change(self, ref, expected, *, data=None, revision=None, activate=False, actor=None):
        with self.engine.begin() as conn:
            record = self._product(conn, ref, lock=True)
            if record["current_revision"] != expected:
                raise AuthoringConflict("This product changed; reload its history before saving")
            current = _sql(conn, """SELECT * FROM scope_revisions WHERE product_id=:id
                ORDER BY (id=:current) DESC,created_at DESC,id LIMIT 1""", id=record["id"], current=expected).mappings().first()
            if current is None:
                raise KeyError("Product has no revisions")
            if revision is not None:
                source = _sql(conn, "SELECT * FROM scope_revisions WHERE id=:id AND product_id=:product",
                    id=revision, product=record["id"]).mappings().first()
                if source is None:
                    raise KeyError("Product revision not found")
                data = source["data"]
                provenance = {**source["provenance"], "activated_revision": revision}
            else:
                data = validate_product_edit(current["data"], data)
                provenance = dict(current["provenance"])
            rid, created = str(uuid.uuid4()), datetime.now(UTC).isoformat()
            _sql(conn, """INSERT INTO scope_revisions(id,product_id,parent,origin,created_at,actor_id,data,provenance)
                VALUES (:id,:product,:parent,'human',:created,:actor,CAST(:data AS jsonb),CAST(:provenance AS jsonb))""",
                id=rid, product=record["id"], parent=expected, created=created, actor=actor,
                data=json.dumps(data), provenance=json.dumps(provenance))
            if activate:
                _sql(conn, "UPDATE scope_products SET current_revision=:revision,title=:title,artifact_type=:type WHERE id=:id",
                    revision=rid, title=str(data.get("title") or record["title"]), type=record["artifact_type"], id=record["id"])
        return ProductRevision(rid, expected, "human", data, provenance, created, actor, True)

    def save(self, product: ProductRef, data: dict, *, expected_revision: str | None,
             activate: bool = False, actor_id: str | None = None) -> ProductRevision:
        return self._change(product, expected_revision, data=data, activate=activate, actor=actor_id)

    def activate(self, product: ProductRef, revision_id: str, *, expected_revision: str | None,
                 actor_id: str | None = None) -> ProductRevision:
        return self._change(product, expected_revision, revision=revision_id, activate=True, actor=actor_id)


class PostgresCollectionStore:
    def __init__(self, engine, *, actor_id: str | None = None, visibility: str = "shared"):
        if engine.dialect.name != "postgresql" or visibility not in {"shared", "private"}:
            raise ValueError("PostgreSQL and a valid collection visibility are required")
        if visibility == "private" and actor_id is None:
            raise ValueError("A private collection requires an owner context")
        self.engine, self.actor_id, self.visibility = engine, actor_id, visibility

    def _raw(self, conn, identity, *, lock=False):
        validate_identifier(identity)
        return _sql(conn, """SELECT * FROM collections WHERE id=:id
            AND (visibility='shared' OR owner_id=:actor)""" + (" FOR UPDATE" if lock else ""),
            id=identity, actor=self.actor_id).mappings().first()

    @staticmethod
    def _record(row):
        return collection_record({k: v for k, v in row.items() if k != "members"}, row["members"])

    def get(self, collection_id: str) -> CollectionRecord | None:
        with self.engine.connect() as conn:
            row = self._raw(conn, collection_id)
            return self._record(row) if row else None

    def list(self) -> tuple[CollectionRecord, ...]:
        with self.engine.connect() as conn:
            rows = _sql(conn, "SELECT * FROM collections WHERE visibility='shared' OR owner_id=:actor", actor=self.actor_id).mappings()
            return tuple(sorted((self._record(row) for row in rows), key=lambda row: (row.name, row.collection_id)))

    def create(self, name: str, *, description: str | None = None,
               collection_id: str | None = None) -> CollectionRecord:
        if not name.strip():
            raise ValueError("Collection name is required")
        identity = collection_id or "col-" + uuid.uuid4().hex[:12]
        validate_identifier(identity)
        with self.engine.begin() as conn:
            # Serialize duplicate-ID checks even when the existing row is private.
            _sql(conn, "SELECT pg_advisory_xact_lock(hashtextextended(:key,0))", key="osii-collection:" + identity)
            if _sql(conn, "SELECT id FROM collections WHERE id=:id", id=identity).first():
                raise AuthoringConflict("Collection already exists")
            _sql(conn, """INSERT INTO collections(id,name,description,members,owner_id,visibility)
                VALUES (:id,:name,:description,'[]',:owner,:visibility)""", id=identity, name=name.strip(),
                description=description or "", owner=self.actor_id, visibility=self.visibility)
        return self.get(identity)

    def _change(self, identity, expected, *, name=None, description=None, members=None):
        with self.engine.begin() as conn:
            raw = self._raw(conn, identity, lock=True)
            if raw is None:
                raise KeyError("Collection not found")
            if self._record(raw).version != expected:
                raise AuthoringConflict("Collection changed; refresh before editing")
            if members is not None:
                _sql(conn, "UPDATE collections SET members=CAST(:members AS jsonb) WHERE id=:id",
                    id=identity, members=json.dumps(normalized_members(members)))
            else:
                if name is not None and not name.strip():
                    raise ValueError("Collection name is required")
                _sql(conn, "UPDATE collections SET name=:name,description=:description WHERE id=:id",
                    id=identity, name=name.strip() if name is not None else raw["name"],
                    description=description if description is not None else raw["description"])
            row = self._raw(conn, identity)
            return self._record(row)

    def update(self, collection_id: str, *, expected_version: str, name: str | None = None,
               description: str | None = None) -> CollectionRecord:
        return self._change(collection_id, expected_version, name=name, description=description)

    def replace_members(self, collection_id: str, member_ids, *, expected_version: str) -> CollectionRecord:
        return self._change(collection_id, expected_version, members=member_ids)
