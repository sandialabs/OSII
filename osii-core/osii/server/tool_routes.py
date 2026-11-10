"""Hosted adapters for the shared scope tools, product editors and overview."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone, timedelta
import hashlib
from pathlib import PurePosixPath
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from sqlalchemy import select, func

from osii.persistence.postgres import chunks
from osii.persistence.scope_products import ScopeProducts
from osii.processor_sdk.models import StandardArtifactData
from osii.server.auth import require
from osii.server.intake import configuration_stamp, public_run
from osii.server.library_tools import tool_catalog, submit, scoped_headers, input_state


class Scope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope_type: Literal["root", "folder", "collection", "object"] = "root"
    folder_id: str | None = Field(default=None, max_length=4096)
    collection_id: str | None = Field(default=None, max_length=200)
    file_id: str | None = Field(default=None, max_length=200)


class ScopeBody(BaseModel):
    scope: Scope


class ToolRequest(ScopeBody):
    model_config = ConfigDict(extra="forbid")
    enricher_name: str = Field(max_length=200)
    enricher_config: dict = Field(default_factory=dict)
    model_bindings: dict[str, str] = Field(default_factory=dict)
    expert_context: str = Field(default="", max_length=8000)


class ProductRequest(ScopeBody):
    filename: str = Field(max_length=200)
    family: Literal["synthesis", "enrichment"] | None = None
    expected_revision: str | None = Field(default=None, max_length=100)


class ProductChange(ProductRequest):
    markdown: str | None = Field(default=None, max_length=2_000_000)
    data: dict | None = None
    revision: str | None = Field(default=None, max_length=100)


def register_tool_routes(app, store, settings):
    router = APIRouter(tags=["library tools"])
    reader, editor, admin = require(), require("curator"), require("admin")
    products = ScopeProducts(store)

    def checked(function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except KeyError:
            raise HTTPException(404, "Scope, run or product not found") from None
        except FileExistsError as exc:
            raise HTTPException(409, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    def scope_rows(scope, actor):
        return checked(scoped_headers, store, scope, actor["id"])

    def permissions(actor):
        return {
            "edit": actor["role"] in {"admin", "curator"},
            "run": actor["role"] == "admin",
        }

    def history(scope, name, actor):
        scope_rows(scope, actor)
        result = checked(products.history, scope, name)
        current = next(
            row for row in result["revisions"] if row["id"] == result["current"]
        )
        return {
            **result,
            "library_id": hashlib.sha256(
                ("hosted:" + actor["id"]).encode()
            ).hexdigest()[:20],
            "permissions": permissions(actor),
            "input_state": input_state(
                store, scope, current["provenance"], actor["id"]
            ),
        }

    @router.get("/api/enrichment-jobs/tools")
    def tools(actor=Depends(reader)):
        return tool_catalog(store, settings, actor)

    @router.post("/api/enrichment-jobs/run")
    def run_tool(payload: ToolRequest, actor=Depends(admin)):
        return checked(submit, store, settings, actor, payload.model_dump())

    @router.post("/api/products/list")
    def product_list(scope: Scope, actor=Depends(reader)):
        value = scope.model_dump(exclude_none=True)
        scope_rows(value, actor)
        return {"products": products.records(value), "permissions": permissions(actor)}

    @router.post("/api/enrichments/list")
    def enrichment_list(scope: Scope, actor=Depends(reader)):
        value = scope.model_dump(exclude_none=True)
        scope_rows(value, actor)
        return {
            "scope": value,
            "permissions": permissions(actor),
            "enrichments": [
                {
                    **row,
                    "kind": "file",
                    "name": row["filename"],
                    "relpath": row["filename"],
                    "can_edit": permissions(actor)["edit"],
                }
                for row in products.records(value)
            ],
        }

    @router.post("/api/enrichments/payload")
    def payload_read(payload: ProductRequest, actor=Depends(reader)):
        value = history(
            payload.scope.model_dump(exclude_none=True), payload.filename, actor
        )
        return {
            "filename": payload.filename,
            "relpath": payload.filename,
            "data": value["data"],
        }

    @router.delete("/api/enrichments/payload")
    def payload_delete(payload: ProductRequest, actor=Depends(editor)):
        value = payload.scope.model_dump(exclude_none=True)
        scope_rows(value, actor)
        if not payload.expected_revision:
            raise HTTPException(409, "Refresh the product before deleting it")
        checked(products.delete, value, payload.filename, payload.expected_revision)
        store.record("scope_product_deleted", actor["id"], payload.filename)
        return {"filename": payload.filename, "deleted": True, "metadata_deleted": True}

    @router.post("/api/products/revisions")
    @router.post("/api/enrichments/revisions")
    def revisions(payload: ProductRequest, actor=Depends(reader)):
        return history(
            payload.scope.model_dump(exclude_none=True), payload.filename, actor
        )

    @router.put("/api/products/revisions")
    @router.put("/api/enrichments/revisions")
    def edit(payload: ProductChange, actor=Depends(editor)):
        scope = payload.scope.model_dump(exclude_none=True)
        current = history(scope, payload.filename, actor)
        if (
            sum(
                value is not None
                for value in (payload.markdown, payload.data, payload.revision)
            )
            != 1
        ):
            raise HTTPException(
                422, "Choose one change: markdown, product JSON or a saved revision"
            )
        data = payload.data
        if payload.markdown is not None:
            if current["data"].get("artifact_type") != "wiki_markdown":
                raise HTTPException(422, "This product is not a wiki")
            data = {**current["data"], "markdown": payload.markdown}
        if data is not None:
            if data.get("artifact_type") != current["data"].get("artifact_type"):
                raise HTTPException(422, "Keep the existing product format")
            if data.get("artifact_type") == "text" and not isinstance(
                data.get("text"), str
            ):
                raise HTTPException(422, "Text products require text content")
            if data.get("artifact_type") not in {"text", "json"}:
                try:
                    data = (
                        TypeAdapter(StandardArtifactData)
                        .validate_python(data)
                        .model_dump(mode="json")
                    )
                except ValueError:
                    raise HTTPException(
                        422, "Invalid standard product format"
                    ) from None
            allowed = set(
                next(
                    row
                    for row in current["revisions"]
                    if row["id"] == current["current"]
                )["provenance"].get("member_ids", [])
            )

            def validate_refs(value):
                if isinstance(value, dict):
                    if value.get("file_id") and value["file_id"] not in allowed:
                        raise HTTPException(
                            422,
                            "Product reference falls outside its frozen input scope",
                        )
                    for child in value.values():
                        validate_refs(child)
                elif isinstance(value, list):
                    for child in value:
                        validate_refs(child)

            validate_refs(data)
        checked(
            products.edit,
            scope,
            payload.filename,
            payload.expected_revision,
            actor["id"],
            data=data,
            revision=payload.revision,
        )
        store.record("scope_product_edited", actor["id"], payload.filename)
        return history(scope, payload.filename, actor)

    def visible_job(jid, actor):
        job = store.job(jid)
        if not job or job["kind"] == "inventory_scan":
            raise HTTPException(404, "Run not found")
        if job["kind"] == "tool":
            scope_rows(job["payload"]["scope"], actor)
        elif actor["role"] != "admin":
            raise HTTPException(403, "Processing runs require administrator access")
        return job

    def run_public(job):
        value = public_run(job)
        if job["kind"] == "tool":
            value.update(
                tool_id=job["payload"]["tool_id"],
                tool_label=job["payload"]["tool_label"],
                workflow="tool",
                scope=job["payload"]["scope"],
                error=job["logs"][-1]
                if job["status"] == "error" and job["logs"]
                else None,
                operations={
                    "extract": False,
                    "embed": False,
                    "enrich": job["payload"]["tool_label"],
                },
            )
        return value

    @router.get("/api/runs")
    def runs(actor=Depends(reader)):
        result = []
        for job in store.job_records():
            if job["kind"] == "inventory_scan":
                continue
            try:
                visible_job(job["id"], actor)
            except HTTPException:
                continue
            result.append(run_public(job))
        seen = store.setting("worker_status", {}).get("last_seen")
        available = bool(
            seen
            and datetime.fromisoformat(seen)
            > datetime.now(timezone.utc) - timedelta(seconds=45)
        )
        return {"runs": result, "worker": {"available": available}}

    @router.get("/api/enrichment-jobs/runs/{jid}/batches")
    @router.get("/api/scope-tool-runs/{jid}/batches")
    def batch_details(jid: str, cursor: int = 0, limit: int = 20, actor=Depends(reader)):
        from osii.server.scope_batches import details
        job=visible_job(jid, actor)
        if not job['payload'].get('batch_version'):
            raise HTTPException(404, 'This run has no batch details')
        if cursor < 0 or not 1 <= limit <= 50:
            raise HTTPException(422, 'Invalid batch page')
        return details(store,jid,cursor=cursor,limit=limit)

    @router.get("/api/enrichment-jobs/runs/{jid}/batches/{batch_id}")
    def one_batch(jid: str, batch_id: str, actor=Depends(reader)):
        from osii.server.scope_batches import batch_result
        visible_job(jid, actor)
        return checked(batch_result,store,jid,batch_id)

    @router.get("/api/enrichment-jobs/runs/{jid}/sources")
    def run_sources(jid: str, cursor: int = 0, limit: int = 50, only_missing: bool = False, actor=Depends(reader)):
        from osii.server.scope_batches import source_details
        visible_job(jid, actor)
        if cursor < 0 or not 1 <= limit <= 100:raise HTTPException(422, 'Invalid source page')
        return source_details(store,jid,cursor=cursor,limit=limit,only_missing=only_missing)

    @router.get("/api/runs/{jid}")
    def run_get(jid: str, actor=Depends(reader)):
        return run_public(visible_job(jid, actor))

    @router.get("/api/runs/{jid}/logs")
    def logs(jid: str, actor=Depends(reader)):
        return {"run_id": jid, "logs": visible_job(jid, actor)["logs"]}

    @router.post("/api/runs/{jid}/{action}")
    def control(
        jid: str,
        action: Literal["pause", "resume", "cancel", "retry"],
        actor=Depends(admin),
    ):
        visible_job(jid, actor)
        result = checked(
            store.control_job, jid, action, lambda: configuration_stamp(store, settings)
        )
        store.record("processing_" + action, actor["id"], jid)
        return run_public(result)

    @router.get("/api/scopes/folders")
    def folders(actor=Depends(reader)):
        paths = {"."}
        for row in store.catalog_documents():
            paths.update(
                str(path) for path in PurePosixPath(row["source_relpath"]).parents
            )
        return {
            "scopes": [
                {
                    "scope_type": "folder",
                    "scope_id": path,
                    "folder_id": path,
                    "path": path,
                    "label": path,
                }
                for path in sorted(paths)
            ]
        }

    @router.get("/api/scopes/collections")
    def collections(actor=Depends(reader)):
        return {
            "scopes": [
                {
                    "scope_type": "collection",
                    "scope_id": row["id"],
                    "collection_id": row["id"],
                    "label": row["name"],
                    "description": row["description"],
                    "document_count": len(row["members"]),
                }
                for row in store.collection_records(actor["id"])
            ]
        }

    @router.post("/api/scopes/summaries")
    def summaries(payload: ScopeBody, actor=Depends(reader)):
        scope = payload.scope.model_dump(exclude_none=True)
        rows = scope_rows(scope, actor)
        return {
            "scope": scope,
            "summaries": [
                {
                    **row,
                    "mime": row["media_type"],
                    "collections": [],
                    "processing": {},
                    "has_preferred_text": row["has_text"],
                    "preview_available": True,
                }
                for row in rows
            ],
        }

    @router.post("/api/scopes/overview")
    def overview(payload: ScopeBody, actor=Depends(reader)):
        scope = payload.scope.model_dump(exclude_none=True)
        rows = scope_rows(scope, actor)
        count = len(rows)
        sizes = [row["size_bytes"] for row in rows if row.get("size_bytes") is not None]
        dates = []
        for row in rows:
            try:
                dates.append(
                    datetime.fromisoformat(row["modified_at"]).astimezone(timezone.utc)
                )
            except (ValueError, TypeError, KeyError):
                pass

        def date_summary(values):
            return {
                "recorded_count": len(values),
                "missing_count": count - len(values),
                "earliest": min(values).isoformat() if values else None,
                "latest": max(values).isoformat() if values else None,
                "buckets": [
                    {"label": key, "count": value}
                    for key, value in sorted(
                        Counter(date.strftime("%Y") for date in values).items()
                    )
                ],
            }

        model = store.configuration().get("embedding_model", "")
        with store.engine.connect() as c:
            indexed = (
                c.execute(
                    select(func.count(func.distinct(chunks.c.file_id))).where(
                        chunks.c.file_id.in_([row["file_id"] for row in rows]),
                        chunks.c.embedding_model == model,
                        chunks.c.embedding.is_not(None),
                    )
                ).scalar()
                if model
                else 0
            )
        return {
            "scope": scope,
            "file_count": count,
            "size_known_count": len(sizes),
            "total_size_bytes": sum(sizes),
            "average_size_bytes": sum(sizes) / len(sizes) if sizes else None,
            "missing_metadata_count": count - len(sizes),
            "file_types": [
                {"label": key, "count": value}
                for key, value in Counter(
                    row["media_type"] for row in rows
                ).most_common()
            ],
            "dates": {"created": date_summary([]), "modified": date_summary(dates)},
            "processing": {
                "text_count": sum(row["has_text"] for row in rows),
                "synthesis_count": sum(row["has_synthesis"] for row in rows),
                "enrichment_count": sum(row["has_enrichments"] for row in rows),
                "indexed_count": indexed,
                "semantic_index": {
                    "status": "ready" if indexed else "missing",
                    "detail": "Saved vectors matching the selected model."
                    if indexed
                    else "No matching saved vectors.",
                    "model": model,
                },
            },
            "warnings": [],
            "permissions": permissions(actor),
        }

    app.include_router(router)
