"""Authenticated hosted adapters for the shared inventory and Intake UI."""

from __future__ import annotations
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from osii.domain.processing.directory_browse import DirectoryBrowsers
from osii.persistence.inventory import PostgresInventory
from osii.server.auth import require
from osii.server.intake import plan, public_run
from osii.volume.models import Filters, ScanOptions, SelectionRequest


class SourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root: str = Field(max_length=4096)
    name: str = Field(default="", max_length=200)


class InventoryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selection_id: int | None = Field(default=None, gt=0)
    excluded_paths: list[str] = Field(default_factory=list, max_length=5000)
    paths: list[str] = Field(default_factory=list, max_length=5000)
    operation: Literal["missing", "reprocess", "embed", "process"] = "missing"
    embed: bool = False
    synthesizer_name: str | None = None
    enricher_name: str | None = None
    synthesizer_config: dict = Field(default_factory=dict)
    enricher_config: dict = Field(default_factory=dict)
    expert_context: str = Field(default="", max_length=8000)
    extractor_name: str | None = None
    extractor_config: dict = Field(default_factory=dict)
    extraction_policy: Literal["make_primary", "save_variant"] = "make_primary"


def register_inventory_routes(app, store, settings):
    admin = require("admin")
    inventory = PostgresInventory(store, settings.source_root)
    router = APIRouter(dependencies=[Depends(admin)], tags=["inventory"])
    browsers = DirectoryBrowsers()
    owners = {}
    previous = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with previous(application):
            try:
                yield
            finally:
                browsers.close_all()

    app.router.lifespan_context = lifespan

    def call(function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except KeyError as exc:
            raise HTTPException(404, str(exc.args[0])) from None
        except (ValueError, OSError) as exc:
            detail = (
                str(exc)
                if isinstance(exc, ValueError)
                else f"Source directory unavailable ({type(exc).__name__}); restore the mount and resume"
            )
            raise HTTPException(409, detail) from None

    @router.get("/api/volume/capabilities")
    def capabilities():
        return {
            "mount_root": str(inventory.root),
            "uploads": False,
            "processing": "core-intake",
            "storage": "postgresql",
        }

    @router.get("/api/volume/sources")
    def locations():
        rows = inventory.sources()
        if not rows:
            try:
                rows = [inventory.register(str(inventory.root))]
            except (OSError, ValueError):
                pass
        return {"items": rows}

    @router.post("/api/volume/sources")
    def register(payload: SourceRequest, account=Depends(admin)):
        result = call(inventory.register, payload.root, payload.name)
        store.record("inventory_location_registered", account["id"], str(result["id"]))
        return result

    @router.post("/api/volume/sources/{source_id}/rebind")
    def rebind(source_id: int, payload: SourceRequest, account=Depends(admin)):
        result = call(inventory.rebind, source_id, payload.root)
        store.record("inventory_location_rebound", account["id"], str(source_id))
        return result

    @router.post("/api/volume/sources/{source_id}/scan")
    def scan(
        source_id: int, payload: ScanOptions = ScanOptions(), account=Depends(admin)
    ):
        result = call(inventory.start, source_id, payload)
        store.record("inventory_scan_queued", account["id"], str(result["id"]))
        return result

    @router.get("/api/volume/sources/{source_id}/scans")
    def source_runs(source_id: int):
        call(inventory.source, source_id)
        return {"items": inventory.runs(source_id=source_id, recent=True, limit=20)}

    @router.get("/api/volume/entries")
    def entry_page(
        filters: Filters = Depends(),
        cursor: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
    ):
        return call(inventory.entries, filters, cursor, limit)

    @router.get("/api/volume/summary")
    def summary(filters: Filters = Depends()):
        return call(inventory.summary, filters)

    @router.post("/api/volume/selections")
    def freeze(payload: SelectionRequest, account=Depends(admin)):
        result = call(inventory.select, payload)
        store.record("inventory_batch_frozen", account["id"], str(result["id"]))
        return result

    @router.get("/api/volume/selections")
    def selection_page(
        cursor: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)
    ):
        return {"items": inventory.selections(cursor, limit)}

    @router.get("/api/volume/selections/{selection_id}")
    def selection(selection_id: int):
        return call(inventory.selection, selection_id)

    @router.get("/api/volume/selections/{selection_id}/entries")
    def selected(
        selection_id: int,
        cursor: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
    ):
        return call(inventory.selection_entries, selection_id, cursor, limit)

    @router.get("/api/volume/runs")
    def runs(
        cursor: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        recent: bool = False,
        before: int | None = Query(None, ge=1),
        active_only: bool = False,
        kind: Literal["scan"] | None = None,
    ):
        return {
            "items": inventory.runs(
                cursor=cursor,
                limit=limit,
                recent=recent,
                before=before,
                active_only=active_only,
            )
        }

    @router.get("/api/volume/runs/{run_id}")
    def run(run_id: int):
        return call(inventory.run, run_id)

    @router.get("/api/volume/runs/{run_id}/events")
    def events(
        run_id: int, cursor: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)
    ):
        return {"items": call(inventory.events, run_id, cursor, limit)}

    @router.post("/api/volume/runs/{run_id}/{action}")
    def control(
        run_id: int,
        action: Literal["pause", "resume", "cancel"],
        account=Depends(admin),
    ):
        result = call(inventory.control, run_id, action)
        store.record("inventory_" + action, account["id"], str(run_id))
        return result

    @router.get("/api/browse/roots")
    def roots():
        return {"items": [str(inventory.root)]}

    @router.get("/api/browse/page")
    async def browse(
        request: Request,
        path: str | None = None,
        cursor: str | None = None,
        limit: int = Query(200, ge=1, le=500),
        account=Depends(admin),
    ):
        token = cursor
        try:
            if token:
                if owners.get(token) != account["id"]:
                    raise HTTPException(404, "Folder browser not found")
            else:
                # The child repeats strict, no-follow validation and owns the
                # directory handle; a blocked mount never blocks the API loop.
                raw = str(inventory.root / inventory.relative(path or "."))
                token = browsers.open(
                    raw, inventory.root, inventory.root, "mounted_strict", "", False
                )
                owners[token] = account["id"]
                for expired in set(owners) - set(browsers.sessions):
                    owners.pop(expired, None)
            result = await browsers.page(token, limit, request.is_disconnected)
            if not result.get("cursor"):
                owners.pop(token, None)
            if result.get("error"):
                raise HTTPException(result.get("status", 409), result["error"])
            return result
        except (KeyError, ValueError, TimeoutError, OSError) as exc:
            if token:
                owners.pop(token, None)
            raise HTTPException(409, str(exc)) from None

    @router.delete("/api/browse/page/{token}")
    def close(token: str, account=Depends(admin)):
        if owners.get(token) != account["id"]:
            raise HTTPException(404, "Folder browser not found")
        browsers.close(token)
        owners.pop(token, None)
        return {"closed": True}

    def reviewed(payload):
        options = payload.model_dump(
            exclude={"selection_id", "paths", "excluded_paths"}
        )
        frozen = []
        if payload.selection_id is not None:
            if payload.paths:
                raise ValueError(
                    "Use frozen inventory members or direct paths, not both"
                )
            frozen = inventory.verify_members(payload.selection_id)
            frozen = [
                member
                for member in frozen
                if member["source_relpath"] not in set(payload.excluded_paths)
            ]
            paths = [member["source_relpath"] for member in frozen]
        else:
            paths = [inventory.relative(path) for path in payload.paths]
        if not paths:
            raise ValueError("Choose files or a frozen inventory batch first")
        options["embed"] = options["embed"] or options["operation"] == "embed"
        result = plan(store, settings, paths, **options)
        if frozen:
            result.update(
                inventory_selection_id=payload.selection_id, inventory_members=frozen
            )
        return result

    @router.post("/api/admin/inventory/intake/preview")
    def preview(payload: InventoryPlan):
        return call(reviewed, payload)

    @router.post("/api/admin/inventory/intake/stage")
    def stage(payload: InventoryPlan, account=Depends(admin)):
        result = call(reviewed, payload)
        jid = store.enqueue("plan", result, status="staged")
        store.record("inventory_processing_staged", account["id"], jid)
        return public_run(store.job(jid))

    app.include_router(router)
