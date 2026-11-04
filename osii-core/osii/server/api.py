"""Authenticated HTTP adapters over Core library and persistence operations."""
from __future__ import annotations

from contextlib import asynccontextmanager
import secrets
import hashlib
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from osii.domain.library import Library
from osii.persistence.postgres import PostgresStore, identifier
from osii.server.auth import (COOKIE, CSRF_COOKIE, digest, origin_check, password_hash,
                              public_account, require, verify)
from osii.server.config import Settings
from osii.model_provider import ModelProvider, ProviderError


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=128)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=15, max_length=128)


class AccountCreate(BaseModel):
    username: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,99}$")
    role: Literal["reader", "curator", "admin"] = "reader"


class AccountUpdate(BaseModel):
    role: Literal["reader", "curator", "admin"] | None = None
    active: bool | None = None


class ModelChoices(BaseModel):
    chat_model: str = Field(default="", max_length=200)
    embedding_model: str = Field(default="", max_length=200)


class Search(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    mode: Literal["lexical", "semantic", "hybrid"] = "hybrid"
    top_k: int = Field(default=10, ge=1, le=50)
    scope: dict = Field(default_factory=lambda: {"scope_type": "root"})
    group_by: Literal["file"] | None = None


class Chat(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    scope: dict = Field(default_factory=lambda: {"scope_type": "root"})
    history: list[dict] = Field(default_factory=list, max_length=12)


class Collection(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str = Field(default="", max_length=4000)
    members: list[str] = Field(default_factory=list, max_length=10000)


class Ingest(BaseModel):
    force: bool = False


def create_app(settings: Settings | None = None, store: PostgresStore | None = None,
               provider: ModelProvider | None = None) -> FastAPI:
    settings = settings or Settings.environment()
    store = store or PostgresStore(settings.database_url)
    provider = provider or ModelProvider(settings.model_url, settings.model_key)

    @asynccontextmanager
    async def lifespan(app):
        store.ready()  # Explicit migration required. Never create schema at import.
        if not settings.source_root.is_dir():
            raise RuntimeError("The configured source directory is unavailable")
        yield
        store.engine.dispose()

    app = FastAPI(title="OSII Server", lifespan=lifespan)
    app.state.store, app.state.settings = store, settings
    library = Library(store, provider)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if request.url.path not in {"/health", "/ready", "/api/auth/login"}:
            try:
                await run_in_threadpool(require(password_change=request.url.path in {"/api/auth/me", "/api/auth/password", "/api/auth/logout"}), request)
                if request.url.path in {"/docs", "/redoc", "/openapi.json"}:
                    require("admin")(request)
            except HTTPException as exc:
                return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(IntegrityError)
    async def conflict(request, exc):
        return JSONResponse({"detail": "A record with that identity already exists"}, status_code=409)

    @app.exception_handler(ProviderError)
    async def provider_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=502)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/ready")
    def ready():
        try:
            store.ready()
            return {"status": "ready"}
        except Exception:
            return JSONResponse({"status": "unavailable"}, status_code=503)

    @app.post("/api/auth/login")
    def login(payload: Login, request: Request, response: Response):
        origin_check(request)
        name = payload.username.casefold().strip()
        ip = request.client.host if request.client else "unknown"
        if not store.login_allowed("login-ip:" + ip, failed=True, maximum=60, seconds=60):
            raise HTTPException(429, "Too many login attempts; try again later")
        attempt_key = digest(name + ":" + (request.client.host if request.client else "unknown"))
        if not store.login_allowed(attempt_key):
            raise HTTPException(429, "Too many login attempts; try again in 15 minutes")
        account = store.account(username=name)
        valid = verify(account["password_hash"] if account else None, payload.password)
        if not account or not valid or not account["active"]:
            store.login_allowed(attempt_key, failed=True)
            store.record("login_denied")
            raise HTTPException(401, "Invalid username or password")
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        store.create_session(account["id"], digest(token), digest(csrf), account["auth_version"])
        response.set_cookie(COOKIE, token, httponly=True, secure=settings.secure_cookies, samesite="lax", max_age=43200)
        response.set_cookie(CSRF_COOKIE, csrf, httponly=False, secure=settings.secure_cookies, samesite="lax", max_age=43200)
        store.record("login", account["id"])
        return {"user": public_account(account), "csrf_token": csrf}

    @app.get("/api/auth/me")
    def me(account=Depends(require(password_change=True))):
        return {"user": public_account(account)}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response, account=Depends(require(password_change=True))):
        store.delete_session(digest(request.cookies.get(COOKIE, "")))
        response.delete_cookie(COOKIE)
        response.delete_cookie(CSRF_COOKIE)
        return {"logged_out": True}

    @app.post("/api/auth/password")
    def change_password(payload: PasswordChange, account=Depends(require(password_change=True))):
        stored = store.account(user_id=account["id"])
        if not verify(stored["password_hash"], payload.current_password):
            raise HTTPException(403, "Current password is incorrect")
        store.change_account(account["id"], {"password_hash": password_hash(payload.new_password), "must_change_password": False})
        store.record("password_changed", account["id"])
        return {"sign_in_required": True}

    @app.get("/api/capabilities")
    def capabilities(account=Depends(require())):
        return {"deployment": "server", "role": account["role"], "shared_dataset": True,
            "workflows": ["browse", "search", "chat", "collections", "source-preview"],
            "private_saved_work": False, "uploads": False}

    @app.get("/api/catalog/files")
    def files(limit: int = 100, cursor: str | None = None, account=Depends(require())):
        _, documents, _ = store.snapshot()
        documents.sort(key=lambda d: d["source_relpath"])
        start = int(cursor or 0)
        if start < 0:
            raise ValueError("Cursor must be nonnegative")
        page = documents[start:start + min(max(limit, 1), 500)]
        return {"items": [{k: d[k] for k in ("file_id", "filename", "source_relpath", "media_type", "size_bytes")} for d in page],
            "total": len(documents), "next_cursor": str(start + len(page)) if start + len(page) < len(documents) else None}

    @app.get("/api/catalog/folders")
    def folders(account=Depends(require())):
        _, documents, _ = store.snapshot()
        paths = sorted({str(Path(d["source_relpath"]).parent) for d in documents})
        return {"items": [{"folder_id": p, "path": p} for p in paths], "total": len(paths)}

    @app.get("/api/objects/{file_id}")
    def document(file_id: str, account=Depends(require())):
        doc = store.document(file_id)
        if not doc:
            raise HTTPException(404, "Document not found")
        return doc

    @app.get("/api/objects/{file_id}/texts/preferred")
    def preferred(file_id: str, account=Depends(require())):
        doc = document(file_id, account)
        return {"text": doc["text"], "kind": "canonical_extracted_text", "file_id": file_id}

    @app.get("/api/objects/{file_id}/source")
    def source(file_id: str, account=Depends(require())):
        doc = document(file_id, account)
        target = (settings.source_root / doc["source_relpath"]).resolve()
        if not target.is_relative_to(settings.source_root) or not target.is_file():
            raise HTTPException(404, "Source unavailable")
        if hashlib.sha256(target.read_bytes()).hexdigest() != doc["sha256"]:
            raise HTTPException(409, "The original changed since ingestion; ask a curator to refresh the dataset")
        store.record("source_access", account["id"], file_id)
        # Raw HTML/SVG must not execute under the application's authenticated origin.
        return FileResponse(target, media_type=doc["media_type"], filename=doc["filename"],
            content_disposition_type="inline" if doc["media_type"] == "application/pdf" else "attachment")

    @app.get("/api/objects/{file_id}/artifacts")
    def artifact_list(file_id: str, account=Depends(require())):
        document(file_id, account)
        return {"items": store.list_artifacts(file_id)}

    @app.post("/api/search")
    def search(payload: Search, account=Depends(require())):
        if payload.mode != "lexical" and store.configuration().get("embedding_model"):
            if not store.login_allowed("search:" + account["id"], failed=True, maximum=20) or not store.login_allowed("search:global", failed=True, maximum=200):
                raise HTTPException(429, "Semantic search limit reached; use lexical search or try again in 15 minutes")
        result = library.search(payload.query, payload.mode, payload.top_k, payload.scope)
        if payload.group_by == "file":
            seen = set()
            result["results"] = [r for r in result["results"] if not (r["file_id"] in seen or seen.add(r["file_id"]))]
        return result

    @app.get("/api/search")
    def search_get(q: str, top_k: int = 10, account=Depends(require())):
        return search(Search(query=q, top_k=top_k), account)

    @app.post("/api/chat")
    def chat(payload: Chat, account=Depends(require())):
        if sum(len(str(turn.get("content", ""))) for turn in payload.history) > 12000:
            raise HTTPException(422, "Conversation history is too large")
        # Shared database-backed budget guard; paid generation is never anonymous.
        budget = "chat:" + account["id"]
        if not store.login_allowed(budget, failed=True) or not store.login_allowed("chat:global", failed=True, maximum=100):
            raise HTTPException(429, "Chat limit reached; try again in 15 minutes")
        return library.chat(payload.query, payload.scope, payload.history)

    @app.get("/api/collections")
    def list_collections(account=Depends(require())):
        return {"items": store.collection_records()}

    @app.post("/api/collections")
    def collection_create(payload: Collection, account=Depends(require("curator"))):
        known = {d["file_id"] for d in store.snapshot()[1]}
        if not set(payload.members) <= known:
            raise HTTPException(422, "Collection contains an unknown document")
        value = {"id": identifier(), **payload.model_dump()}
        store.save_collection(value)
        store.record("collection_created", account["id"], value["id"])
        return value

    @app.get("/api/admin/users")
    def accounts(account=Depends(require("admin"))):
        return {"users": [public_account(u) for u in store.list_accounts()]}

    @app.post("/api/admin/users")
    def account_create(payload: AccountCreate, account=Depends(require("admin"))):
        password = secrets.token_urlsafe(24)
        uid = store.create_account(payload.username, password_hash(password), payload.role)
        store.record("account_created", account["id"], uid)
        return {"user": public_account(store.account(user_id=uid)), "temporary_password": password}

    @app.patch("/api/admin/users/{uid}")
    def account_update(uid: str, payload: AccountUpdate, account=Depends(require("admin"))):
        store.change_account(uid, payload.model_dump(exclude_none=True))
        store.record("account_changed", account["id"], uid)
        return {"user": public_account(store.account(user_id=uid))}

    @app.post("/api/admin/users/{uid}/reset-password")
    def account_reset(uid: str, account=Depends(require("admin"))):
        password = secrets.token_urlsafe(24)
        store.change_account(uid, {"password_hash": password_hash(password), "must_change_password": True})
        store.record("password_reset", account["id"], uid)
        return {"temporary_password": password}

    @app.get("/api/admin/models")
    def model_configuration(account=Depends(require("admin"))):
        return {**store.configuration(), "base_url": settings.model_url,
            "credential_present": bool(settings.model_key), "credential_managed_by_deployment": True}

    @app.put("/api/admin/models")
    def model_choices(payload: ModelChoices, account=Depends(require("admin"))):
        store.save_configuration(payload.model_dump())
        store.record("model_selection_changed", account["id"])
        return payload

    @app.get("/api/admin/models/catalog")
    def catalog(account=Depends(require("admin"))):
        return {"models": provider.catalog(), "generation_tested": False}

    @app.post("/api/admin/models/test")
    def model_test(account=Depends(require("admin"))):
        configuration = store.configuration()
        results = {}
        for capability in ("chat", "embedding"):
            model = configuration.get(capability + "_model")
            if not model:
                results[capability] = {"configured": False}
                continue
            try:
                if capability == "chat":
                    provider.chat(model, [{"role": "user", "content": "Reply with the word connected."}], max_tokens=24)
                else:
                    provider.embed(model, ["OSII synthetic connection check"])
                results[capability] = {"configured": True, "ok": True}
            except ProviderError as exc:
                results[capability] = {"configured": True, "ok": False, "detail": str(exc)}
        return results

    @app.post("/api/admin/intake")
    def intake(payload: Ingest | None = None, account=Depends(require("curator"))):
        jid = store.enqueue("ingest", payload.model_dump() if payload else {})
        store.record("ingestion_requested", account["id"], jid)
        return {"id": jid, "status": "queued"}

    @app.get("/api/runs")
    def runs(account=Depends(require("curator"))):
        return {"runs": store.job_records()}

    return app
