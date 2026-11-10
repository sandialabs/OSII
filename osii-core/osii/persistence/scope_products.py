"""Versioned hosted knowledge products; scope visibility is checked by Core."""

from __future__ import annotations
import hashlib
import json
import uuid
from sqlalchemy import select, insert, update, delete
from osii.persistence.postgres import identifier, now, jobs
from osii.persistence.workspace_schema import (
    scope_products as products,
    scope_revisions as revisions,
)


def address(scope: dict) -> tuple[str, str]:
    kind = scope.get("scope_type", "root")
    if kind not in {"root", "object", "folder", "collection"}:
        raise ValueError("Unsupported scope")
    key = {
        "object": "file_id",
        "folder": "folder_id",
        "collection": "collection_id",
    }.get(kind)
    value = "root" if kind == "root" else str(scope.get(key) or "").strip()
    if not value or len(value) > 4096:
        raise ValueError("Choose a scope identifier")
    if kind == "folder":
        value = value.strip("/") or "."
    return kind, value


def filename(method: str, output: str) -> str:
    return (
        "tool-"
        + hashlib.sha256(f"{method}:{output}".encode()).hexdigest()[:24]
        + ".json"
    )


class ScopeProducts:
    def __init__(self, store):
        self.store = store

    def records(self, scope):
        kind, identity = address(scope)
        with self.store.engine.connect() as c:
            return [
                dict(row)
                for row in c.execute(
                    select(products)
                    .where(
                        products.c.scope_type == kind, products.c.scope_id == identity
                    )
                    .order_by(products.c.filename)
                ).mappings()
            ]

    def parents(self, scope, method):
        return {
            row["filename"]: row["current_revision"]
            for row in self.records(scope)
            if row["method"] == method
        }

    def history(self, scope, name, c=None):
        if c is None:
            with self.store.engine.connect() as connection:
                return self.history(scope, name, connection)
        kind, identity = address(scope)
        product = (
            c.execute(
                select(products).where(
                    products.c.scope_type == kind,
                    products.c.scope_id == identity,
                    products.c.filename == name,
                )
            )
            .mappings()
            .first()
        )
        if product is None:
            raise KeyError("Product not found")
        history = [
            dict(row)
            for row in c.execute(
                select(revisions)
                .where(revisions.c.product_id == product["id"])
                .order_by(revisions.c.created_at, revisions.c.id)
            ).mappings()
        ]
        current = next(
            (row for row in history if row["id"] == product["current_revision"]), None
        )
        if current is None:
            raise ValueError("Product revision history is incomplete")
        for row in history:
            row["grounding_needs_review"] = row["origin"] == "human"
        return {
            **dict(product),
            "current": current["id"],
            "data": current["data"],
            "revisions": history,
        }

    def generated(self, scope, method, outputs, job, worker, provenance):
        from sqlalchemy.dialects.postgresql import insert as upsert

        kind, identity = address(scope)
        parents = job["payload"].get("product_parents", {})
        with self.store.transaction() as c:
            self.store.assert_job_owner(c, (job["id"], worker))
            for output in outputs:
                name = filename(method, output["id"])
                data = output["data"]
                statement = upsert(products).values(
                    id=identifier(),
                    scope_type=kind,
                    scope_id=identity,
                    filename=name,
                    family=output["family"],
                    method=method,
                    title=str(data.get("title") or output["id"]),
                    artifact_type=str(data.get("artifact_type") or "json"),
                )
                c.execute(
                    statement.on_conflict_do_nothing(constraint="scope_product_address")
                )
                product = (
                    c.execute(
                        select(products)
                        .where(
                            products.c.scope_type == kind,
                            products.c.scope_id == identity,
                            products.c.filename == name,
                        )
                        .with_for_update()
                    )
                    .mappings()
                    .one()
                )
                rid = str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"osii:scope-product:{job['id']}:{output['id']}",
                    )
                )
                if c.execute(
                    select(revisions.c.id).where(revisions.c.id == rid)
                ).first():
                    continue
                parent = parents.get(name)
                # Newly created products have no previous parent. A generation
                # never overwrites a human revision or a change made mid-run.
                current = c.execute(
                    select(revisions.c.origin).where(
                        revisions.c.id == product["current_revision"]
                    )
                ).scalar()
                c.execute(
                    insert(revisions).values(
                        id=rid,
                        product_id=product["id"],
                        parent=parent,
                        origin="generated",
                        created_at=now().isoformat(),
                        actor_id=job["payload"]["actor_id"],
                        data=data,
                        provenance=provenance,
                    )
                )
                if product["current_revision"] is None or (
                    product["current_revision"] == parent and current != "human"
                ):
                    c.execute(
                        update(products)
                        .where(products.c.id == product["id"])
                        .values(
                            current_revision=rid,
                            title=str(data.get("title") or product["title"]),
                            artifact_type=str(
                                data.get("artifact_type") or product["artifact_type"]
                            ),
                        )
                    )

            payload = dict(
                c.execute(
                    select(jobs.c.payload).where(jobs.c.id == job["id"])
                ).scalar_one()
            )
            payload["items"][0].update(status="done", finished_at=now().isoformat())
            c.execute(
                update(jobs).where(jobs.c.id == job["id"]).values(payload=payload)
            )

    def edit(self, scope, name, expected, actor, *, data=None, revision=None):
        kind, identity = address(scope)
        with self.store.transaction() as c:
            product = (
                c.execute(
                    select(products)
                    .where(
                        products.c.scope_type == kind,
                        products.c.scope_id == identity,
                        products.c.filename == name,
                    )
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if product is None:
                raise KeyError("Product not found")
            if product["current_revision"] != expected:
                raise FileExistsError(
                    "This product changed; reload the latest revision before saving"
                )
            current = (
                c.execute(
                    select(revisions).where(
                        revisions.c.id == expected,
                        revisions.c.product_id == product["id"],
                    )
                )
                .mappings()
                .one()
            )
            if revision:
                chosen = (
                    c.execute(
                        select(revisions).where(
                            revisions.c.id == revision,
                            revisions.c.product_id == product["id"],
                        )
                    )
                    .mappings()
                    .first()
                )
                if chosen is None:
                    raise KeyError("Product revision not found")
                # Activation remains a durable editorial event, preserving provenance.
                data, provenance = (
                    chosen["data"],
                    {**chosen["provenance"], "activated_revision": revision},
                )
            else:
                provenance = current["provenance"]
            if (
                not isinstance(data, dict)
                or len(json.dumps(data, allow_nan=False)) > 4_000_000
            ):
                raise ValueError("Product JSON must be an object with at most 4 MiB")
            rid = identifier()
            c.execute(
                insert(revisions).values(
                    id=rid,
                    product_id=product["id"],
                    parent=expected,
                    origin="human",
                    created_at=now().isoformat(),
                    actor_id=actor,
                    data=data,
                    provenance=provenance,
                )
            )
            c.execute(
                update(products)
                .where(products.c.id == product["id"])
                .values(
                    current_revision=rid,
                    title=str(data.get("title") or product["title"]),
                    artifact_type=str(
                        data.get("artifact_type") or product["artifact_type"]
                    ),
                )
            )
            return self.history(scope, name, c)

    def delete(self, scope, name, expected):
        kind, identity = address(scope)
        with self.store.transaction() as c:
            row = (
                c.execute(
                    select(products)
                    .where(
                        products.c.scope_type == kind,
                        products.c.scope_id == identity,
                        products.c.filename == name,
                    )
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if row is None:
                raise KeyError("Product not found")
            if expected != row["current_revision"]:
                raise FileExistsError("Product changed; refresh before deleting")
            c.execute(delete(products).where(products.c.id == row["id"]))
