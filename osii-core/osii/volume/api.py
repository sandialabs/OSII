"""Loopback API for the single-operator volume application; no sidecar routes."""

from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path
import sqlite3
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .models import Filters, ProcessRequest, SelectionRequest, ScanOptions
from .store import VolumeStore, database_path


class SourceRequest(BaseModel):
    root: str
    name: str = ""


def create_app(path: Path | None = None, *, api_prefix: str = "/api/volume") -> FastAPI:
    store = VolumeStore(path or database_path())

    @asynccontextmanager
    async def lifespan(app):
        store.initialize()
        # An existing catalog remains browsable when a registered share disconnects.
        source_root = getattr(
            app.state, "source_root", os.getenv("SHARED_VOLUME_ROOT", "")
        )
        if source_root and Path(source_root).is_dir():
            store.register_source(Path(source_root))
        yield

    app = FastAPI(title="OSII file inventory API", lifespan=lifespan)
    app.state.volume_store = store
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"],
    )

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse(status_code=404, content={"detail": str(exc.args[0])})

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(sqlite3.OperationalError)
    async def database_error(request, exc):
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Canonical database unavailable; check disk space, permissions, and schema. Evidence has not been reset."
            },
        )

    @app.exception_handler(OSError)
    async def source_error(request, exc):
        return JSONResponse(
            status_code=422,
            content={
                "detail": f"Source directory unavailable ({type(exc).__name__}); verify its path and access"
            },
        )

    @app.middleware("http")
    async def same_origin(request: Request, call_next):
        origin = request.headers.get("origin")
        if origin:
            from urllib.parse import urlsplit

            parsed = urlsplit(origin)
            if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
                "localhost",
                "127.0.0.1",
                "::1",
            }:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Only the local dashboard may access this API"},
                )
        return await call_next(request)

    @app.get("/health")
    def health():
        with store.connect() as conn:
            conn.execute("SELECT 1 FROM sources LIMIT 1")
        return {"status": "ok", "storage_mode": "local", "user_authentication": False}

    @app.get("/api/runtime")
    def runtime():
        return {
            "storage_mode": "local",
            "user_authentication": False,
            "database": str(store.path),
        }

    @app.get(api_prefix + "/sources")
    def sources():
        return {"items": store.sources()}

    @app.post(api_prefix + "/sources")
    def register(payload: SourceRequest):
        return store.register_source(Path(payload.root), payload.name)

    @app.post(api_prefix + "/sources/{source_id}/rebind")
    def rebind(source_id: int, payload: SourceRequest):
        return store.rebind_source(source_id, payload.root)

    @app.get(api_prefix + "/sources/{source_id}/scans")
    def source_scans(source_id: int):
        return {"items": store.source_scans(source_id)}

    @app.post(api_prefix + "/sources/{source_id}/scan")
    def scan(source_id: int, payload: ScanOptions = ScanOptions()):
        payload.isolate = True
        return store.run(store.new_scan(source_id, payload))

    @app.get(api_prefix + "/summary")
    def summary(filters: Filters = Depends()):
        return store.summary(filters)

    @app.get(api_prefix + "/entries")
    def entries(
        filters: Filters = Depends(),
        cursor: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
    ):
        return store.entries(filters, cursor, limit)

    @app.get(api_prefix + "/folders")
    def folders(
        source_id: int,
        parent: str = "",
        cursor: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
    ):
        return store.folders(source_id, parent, cursor, limit)

    @app.get(api_prefix + "/entries/{entry_id}")
    def document(entry_id: int):
        return store.document(entry_id)

    @app.get(api_prefix + "/entries/{entry_id}/extractions/{extraction_id}")
    def historical_extraction(entry_id: int, extraction_id: str):
        return store.extraction(entry_id, extraction_id)

    @app.get(api_prefix + "/entries/{entry_id}/original")
    def original(entry_id: int):
        from urllib.parse import quote
        from .processing import read_source

        entry = store.document(entry_id)
        if not entry["extraction_id"] or entry["status"] != "present":
            raise HTTPException(
                409, "No current extraction to verify this original against"
            )
        try:
            content, sha = read_source(
                Path(store.source(entry["source_id"])["root"]), entry, 50 * 1024**2
            )
        except (OSError, ValueError) as exc:
            raise HTTPException(
                409,
                "Source unavailable or changed since extraction; reconnect or scan and extract again",
            ) from exc
        if sha != entry["sha256"]:
            raise HTTPException(409, "Source content changed since extraction")
        return Response(
            content,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(entry['name'])}",
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store",
            },
        )

    @app.get(api_prefix + "/search")
    def search(
        q: str, cursor: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)
    ):
        try:
            return store.search(q, cursor, limit)
        except sqlite3.OperationalError as exc:
            if exc.sqlite_errorcode != sqlite3.SQLITE_ERROR:
                raise
            raise ValueError(
                "Invalid full-text query; use words, quoted phrases, AND, OR, or NOT"
            ) from exc

    @app.post(api_prefix + "/selections")
    def select(payload: SelectionRequest):
        return store.select(payload)

    @app.get(api_prefix + "/selections")
    def selections(cursor: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
        return {"items": store.selections(cursor, limit)}

    @app.get(api_prefix + "/selections/{selection_id}")
    def selection(selection_id: int):
        return store.selection(selection_id)

    @app.get(api_prefix + "/selections/{selection_id}/entries")
    def selection_entries(
        selection_id: int,
        cursor: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
    ):
        return store.selection_entries(selection_id, cursor, limit)

    @app.get(api_prefix + "/products/{product_id}")
    def product(product_id: int):
        return store.product(product_id)

    @app.post(api_prefix + "/runs")
    def process(payload: ProcessRequest):
        return store.run(store.new_processing(payload))

    @app.get(api_prefix + "/runs")
    def runs(cursor: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
        return {"items": store.runs(cursor, limit)}

    @app.get(api_prefix + "/runs/{run_id}")
    def run(run_id: int):
        return store.run(run_id)

    @app.post(api_prefix + "/runs/{run_id}/{action}")
    def control(run_id: int, action: Literal["pause", "resume", "cancel"]):
        return store.control(run_id, action)

    @app.get(api_prefix + "/runs/{run_id}/events")
    def events(
        run_id: int, cursor: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)
    ):
        return {"items": store.events(run_id, cursor, limit)}

    @app.get(api_prefix + "/runs/{run_id}/report")
    def report(run_id: int):
        return store.report(run_id)

    return app
