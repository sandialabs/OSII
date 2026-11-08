"""Authenticated HTTP adapters over Core library and persistence operations."""
from __future__ import annotations

from contextlib import asynccontextmanager
import secrets
import hashlib
import os
import time
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from osii.domain.library import Library
from osii.domain.topics import topic_map, related_documents, TopicIndexUnavailable
from osii.server.sources import browse, resolve_directory
from osii.persistence.postgres import PostgresStore, identifier
from osii.server.auth import (COOKIE, CSRF_COOKIE, digest, origin_check, password_hash,
                              public_account, require, verify)
from osii.server.config import Settings
from osii.model_provider import ModelProvider, ProviderError
from osii.server.model_connections import ModelConnections, ConfiguredModelProvider
from osii.model_catalog import discover_models


class Login(BaseModel):
    remember: bool = False
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


class EndpointChoice(BaseModel):
    base_url: str = Field(max_length=2000)
    model: str | None = Field(default=None, max_length=200)
    model_name: str = Field(default="", max_length=300)
    api_key: str | None = Field(default=None, max_length=4096, repr=False)
    clear_api_key: bool = False


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
    visibility: Literal["private", "shared"] = "private"


class SourceSelection(BaseModel):
    directory: str = Field(default=".", max_length=4000)


class TopicRequest(BaseModel):
    scope: dict = Field(default_factory=lambda: {"scope_type": "root"})


class RelatedRequest(TopicRequest):
    file_id: str = Field(min_length=1, max_length=200)


class ProcessorEndpoints(BaseModel):
    urls: list[str] = Field(default_factory=list, max_length=16)


class ProcessorChat(BaseModel):
    model: str = Field(max_length=200)
    messages: list[dict] = Field(min_length=1, max_length=100)
    max_tokens: int = Field(default=1200, ge=1, le=4000)
    temperature: float | None = Field(default=None, ge=0, le=2)


class ProcessorEmbeddings(BaseModel):
    model: str = Field(max_length=200)
    input: str | list[str]


class IntakePlan(BaseModel):
    paths: list[str] = Field(min_length=1, max_length=5000)
    operation: Literal["missing", "extract", "reprocess", "embed", "process"] = "missing"
    embed: bool = False
    synthesizer_name: str | None = Field(default=None, max_length=200)
    enricher_name: str | None = Field(default=None, max_length=200)
    synthesizer_config: dict = Field(default_factory=dict)
    enricher_config: dict = Field(default_factory=dict)
    expert_context: str = Field(default="", max_length=8000)


class Ingest(BaseModel):
    force: bool = False


def create_app(settings: Settings | None = None, store: PostgresStore | None = None,
               provider: ModelProvider | None = None) -> FastAPI:
    settings = settings or Settings.environment()
    store = store or PostgresStore(settings.database_url)
    connections = ModelConnections(store, settings)
    provider = provider or ConfiguredModelProvider(connections)

    @asynccontextmanager
    async def lifespan(app):
        store.ready()  # Explicit migration required. Never create schema at import.
        if not settings.source_root.is_dir():
            raise RuntimeError("The configured source directory is unavailable")
        yield
        store.engine.dispose()

    app = FastAPI(title="OSII Server", lifespan=lifespan)
    app.state.store, app.state.settings = store, settings
    from osii.rag.strategies.http_reranker import create_reranker
    app.state.rag_reranker = create_reranker(settings.endpoints()["rerank"])
    library = Library(store, provider)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if request.url.path not in {"/health", "/ready", "/api/auth/login",
                "/api/processor-model/v1/models", "/api/processor-model/v1/chat/completions",
                "/api/processor-model/v1/embeddings", "/api/processor-model/v1/tokens/revoke"}:
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

    @app.exception_handler(RequestValidationError)
    async def invalid_fields(request, exc):
        # Validation errors may contain the entire input, including write-only keys.
        fields = [".".join(str(v) for v in error["loc"]) for error in exc.errors()]
        return JSONResponse({"detail": "Invalid request fields: " + ", ".join(fields)}, status_code=422)

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
        lifetime = settings.remember_days * 86400 if payload.remember else 43200
        store.create_session(account["id"], digest(token), digest(csrf), account["auth_version"],
            lifetime_seconds=lifetime, idle_seconds=min(lifetime, 7 * 86400) if payload.remember else 1800)
        response.set_cookie(COOKIE, token, httponly=True, secure=settings.secure_cookies, samesite="lax", max_age=lifetime)
        response.set_cookie(CSRF_COOKIE, csrf, httponly=False, secure=settings.secure_cookies, samesite="lax", max_age=lifetime)
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
            "workflows": ["browse", "search", "chat", "collections", "source-preview", "topics"],
            "private_saved_work": True, "uploads": False}

    @app.get("/api/catalog/files")
    def files(limit: int = 100, cursor: str | None = None, collection_id: str | None = None, folder_id: str | None = None,
              direct: bool = False, account=Depends(require())):
        scope = {"scope_type": "root"}
        if collection_id:
            scope = {"scope_type": "collection", "collection_id": collection_id}
        elif folder_id:
            scope = {"scope_type": "folder", "folder_id": folder_id}
        _, documents, _ = library.scoped(scope, account["id"])
        if direct and not collection_id:
            parent = str(Path(folder_id or "."))
            documents = [d for d in documents if str(Path(d["source_relpath"]).parent) == parent]
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
        paths = sorted({str(parent) for d in documents for parent in Path(d["source_relpath"]).parents})
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
        return {"text": doc["text"], "kind": "canonical_extracted_text", "representation": "primary extraction", "file_id": file_id}

    @app.get("/api/objects/{file_id}/source")
    def source(file_id: str, account=Depends(require())):
        doc = document(file_id, account)
        root = settings.source_root.resolve()
        target = (root / doc["source_relpath"]).resolve()
        if not target.is_relative_to(root) or not target.is_file():
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
        records = store.extraction_records(file_id)
        primary_id = records[0]['id'] if records else None
        rows = store.list_artifacts(file_id)
        for row in rows:
            if row['kind'] in {'synthesis', 'enrichment'}:
                row['stale'] = row['payload'].get('input_extraction_id') != primary_id
        return {"items": sorted(rows, key=lambda row: row['payload'].get('created_at', ''), reverse=True)}

    @app.post("/api/search")
    def search(payload: Search, account=Depends(require())):
        if payload.mode != "lexical" and store.configuration().get("embedding_model"):
            if not store.login_allowed("search:" + account["id"], failed=True, maximum=20) or not store.login_allowed("search:global", failed=True, maximum=200):
                raise HTTPException(429, "Semantic search limit reached; use lexical search or try again in 15 minutes")
        result = library.search(payload.query, payload.mode, payload.top_k, payload.scope, account["id"])
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
        return library.chat(payload.query, payload.scope, payload.history, account["id"])

    def collection_view(value, account):
        return {**value, "can_manage": value["owner_id"] == account["id"] or
            (value["visibility"] == "shared" and account["role"] in {"curator", "admin"})}

    def visible_collection(cid, account):
        value = next((c for c in store.collection_records(account["id"]) if c["id"] == cid), None)
        if value is None:
            raise HTTPException(404, "Collection not found")
        return value

    def validate_collection(payload, account, previous=None):
        if not payload.name.strip():
            raise HTTPException(422, "A collection name is required")
        if payload.visibility == "shared" and account["role"] == "reader":
            raise HTTPException(403, "Only curators and administrators can publish shared collections")
        known = {d["file_id"] for d in store.snapshot()[1]}
        # Preserve references to earlier document versions when editing metadata.
        if previous:
            known.update(previous["members"])
        if not set(payload.members) <= known:
            raise HTTPException(422, "Collection contains an unknown document")
        return {**payload.model_dump(), "name": payload.name.strip(), "members": list(dict.fromkeys(payload.members))}

    @app.get("/api/collections")
    def list_collections(account=Depends(require())):
        return {"items": [collection_view(c, account) for c in store.collection_records(account["id"])]}

    @app.post("/api/collections")
    def collection_create(payload: Collection, account=Depends(require())):
        value = {"id": identifier(), "owner_id": account["id"], **validate_collection(payload, account)}
        store.save_collection(value)
        store.record("collection_created", account["id"], value["id"])
        return collection_view(value, account)

    @app.put("/api/collections/{cid}")
    def collection_update(cid: str, payload: Collection, account=Depends(require())):
        previous = visible_collection(cid, account)
        if not collection_view(previous, account)["can_manage"]:
            raise HTTPException(403, "You cannot change this collection")
        if previous["visibility"] == "shared" and payload.visibility == "private" and previous["owner_id"] != account["id"]:
            raise HTTPException(403, "Only the owner can make a shared collection private")
        value = {**previous, **validate_collection(payload, account, previous)}
        if not store.save_collection(value, previous):
            raise HTTPException(409, "Collection changed; refresh before editing again")
        store.record("collection_changed", account["id"], cid)
        return collection_view(value, account)

    @app.delete("/api/collections/{cid}")
    def collection_delete(cid: str, account=Depends(require())):
        previous = visible_collection(cid, account)
        if not collection_view(previous, account)["can_manage"]:
            raise HTTPException(403, "You cannot delete this collection")
        if not store.delete_collection(previous):
            raise HTTPException(409, "Collection changed; refresh before deleting")
        store.record("collection_deleted", account["id"], cid)
        return {"deleted": True}

    @app.exception_handler(TopicIndexUnavailable)
    async def topics_unavailable(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.post("/api/topics/map")
    def topics(payload: TopicRequest, account=Depends(require())):
        revision, docs, rows = library.scoped(payload.scope, account["id"])
        return topic_map(docs, rows, store.configuration().get("embedding_model", ""), revision)

    @app.post("/api/topics/related")
    def related(payload: RelatedRequest, account=Depends(require())):
        revision, docs, rows = library.scoped(payload.scope, account["id"])
        return related_documents(docs, rows, store.configuration().get("embedding_model", ""), revision, payload.file_id)

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
        return {**store.configuration(), "base_url": connections.endpoints()["chat"].base_url,
            "endpoints": connections.public(),
            "credential_present": bool(connections.endpoints()["chat"].api_key),
            "credential_managed_by_deployment": connections.public()["chat"]["managed_by"] == "deployment"}

    @app.put("/api/admin/models/endpoints/{kind}")
    def endpoint_save(kind: Literal["chat", "embedding", "rerank"], payload: EndpointChoice, account=Depends(require("admin"))):
        if any(job["status"] in {"queued", "running", "pausing", "cancelling"} for job in store.job_records()):
            raise HTTPException(409, "Wait for queued and running processing jobs to finish before changing endpoints")
        result = connections.save(kind, payload.model_dump())
        if kind == "rerank":
            app.state.rag_reranker = create_reranker(connections.endpoints()["rerank"])
        store.record("model_endpoint_changed", account["id"], kind)
        return result

    @app.post("/api/admin/models/endpoints/{kind}/discover")
    def endpoint_discover(kind: Literal["chat", "embedding", "rerank"], payload: EndpointChoice, account=Depends(require("admin"))):
        endpoint = connections.preview(kind, payload.model_dump())
        return {"models": discover_models(endpoint.base_url, endpoint.api_key, capability=kind),
                "generation_tested": False, "saved": False}

    @app.delete("/api/admin/models/endpoints/{kind}")
    def endpoint_reset(kind: Literal["chat", "embedding", "rerank"], account=Depends(require("admin"))):
        if any(job["status"] in {"queued", "running", "pausing", "cancelling"} for job in store.job_records()):
            raise HTTPException(409, "Wait for processing jobs to finish before resetting endpoints")
        connections.reset(kind)
        if kind == "rerank":
            app.state.rag_reranker = create_reranker(connections.endpoints()["rerank"])
        store.record("model_endpoint_reset", account["id"], kind)
        return connections.public()[kind]

    @app.put("/api/admin/models")
    def model_choices(payload: ModelChoices, account=Depends(require("admin"))):
        if any(job["status"] in {"queued", "running", "pausing", "cancelling"} for job in store.job_records()):
            raise HTTPException(409, "Wait for processing jobs to finish before changing models")
        store.save_configuration(payload.model_dump())
        store.record("model_selection_changed", account["id"])
        return payload

    @app.get("/api/admin/models/catalog")
    def catalog(account=Depends(require("admin"))):
        return {"models": provider.catalog(), "warnings": getattr(provider, "catalog_errors", {}), "generation_tested": False}

    @app.post("/api/admin/models/test")
    def model_test(only: Literal["chat", "embedding", "rerank"] | None = None, account=Depends(require("admin"))):
        configuration = store.configuration()
        results = {}
        for capability in ("chat", "embedding"):
            if only and capability != only:
                continue
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
        if only and only != "rerank":
            return results
        endpoint = connections.endpoints()["rerank"]
        results["rerank"] = {"configured": bool(endpoint.base_url and endpoint.model)}
        if endpoint.base_url or endpoint.model:
            from osii.rag.strategies.contracts import Evidence, RerankRequest, StrategyError
            from osii.rag.strategies.http_reranker import create_reranker
            try:
                reranker = create_reranker(endpoint)
                reranker(RerankRequest("connection check", (Evidence("check", "synthetic", "OSII synthetic connection check"),), top_k=1))
                results["rerank"] = {"configured": True, "ok": True}
            except (StrategyError, ValueError) as exc:
                results["rerank"] = {"configured": True, "ok": False, "detail": str(exc)}
        return results

    @app.get("/api/admin/source")
    def source_status(account=Depends(require("admin"))):
        selection = store.setting("source", {"directory": "."})
        try:
            target = resolve_directory(settings.source_root, selection["directory"])
            available, readable = True, os.access(target, os.R_OK | os.X_OK)
        except (ValueError, OSError):
            available, readable = False, False
        return {"mount_root": str(settings.source_root), **selection, "available": available,
            "readable": readable, "statistics": store.statistics(), "models": store.configuration(),
            "extractor_url": settings.extractor_url, "ocr_configured": bool(settings.ocr_url)}

    @app.get("/api/admin/source/browse")
    def source_browse(path: str = ".", cursor: int = 0, account=Depends(require("admin"))):
        try:
            return browse(settings.source_root, path, cursor)
        except OSError:
            raise HTTPException(409, "The source folder is unavailable or unreadable")

    @app.put("/api/admin/source")
    def source_select(payload: SourceSelection, account=Depends(require("admin"))):
        try:
            target = resolve_directory(settings.source_root, payload.directory)
            if not os.access(target, os.R_OK | os.X_OK):
                raise HTTPException(409, "The source folder is unreadable")
        except OSError:
            raise HTTPException(409, "The source folder is unavailable")
        value = {"directory": target.relative_to(settings.source_root.resolve()).as_posix()}
        store.save_setting("source", value)
        store.record("source_selection_changed", account["id"], value["directory"])
        return source_status(account)

    @app.get("/api/admin/processors")
    def processors(account=Depends(require("admin"))):
        from osii.server.processors import catalog, configured_urls
        return {"processors": catalog(store, settings), "urls": configured_urls(store, settings)}

    @app.put("/api/admin/processors")
    def processor_endpoints(payload: ProcessorEndpoints, account=Depends(require("admin"))):
        from osii.server.processors import validate_urls
        store.save_processor_urls(validate_urls(payload.urls))
        store.record("processor_endpoints_changed", account["id"])
        return processors(account)

    def processor_claim(request: Request, capability=None, model="", consume=False):
        from osii.server.processor_gateway import grant_id
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer ") or len(authorization) > 200:
            raise HTTPException(401, "A valid processor model grant is required")
        try:
            key = grant_id(authorization[7:])
            return key, store.processor_grant(key, capability=capability, model=model, consume=consume)
        except ValueError:
            raise HTTPException(403, "Processor grant is expired, exhausted, or outside its allowed model/job")

    @app.get("/api/processor-model/v1/models")
    def processor_models(request: Request):
        _, claims = processor_claim(request)
        return {"object": "list", "data": [{"id": model, "object": "model"} for model in claims["bindings"].values()]}

    @app.post("/api/processor-model/v1/tokens/revoke")
    def processor_revoke(request: Request):
        key, _ = processor_claim(request)
        store.delete_setting(key)
        return {"revoked": True}

    @app.post("/api/processor-model/v1/chat/completions")
    def processor_chat(payload: ProcessorChat, request: Request):
        if sum(len(str(message.get("content", ""))) for message in payload.messages) > 200_000 or any(
            message.get("role") not in {"system", "user", "assistant"} or not isinstance(message.get("content"), str) for message in payload.messages):
            raise HTTPException(422, "Processor messages exceed the supported text/role limits")
        processor_claim(request, "chat", payload.model, True)
        content, usage = provider.chat(payload.model, payload.messages, max_tokens=payload.max_tokens,
            **({"temperature": payload.temperature} if payload.temperature is not None else {}))
        return {"id": "osii-processor", "object": "chat.completion", "created": int(time.time()), "model": payload.model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {k: v for k, v in usage.items() if v is not None}}

    @app.post("/api/processor-model/v1/embeddings")
    def processor_embeddings(payload: ProcessorEmbeddings, request: Request):
        values = [payload.input] if isinstance(payload.input, str) else payload.input
        if not 1 <= len(values) <= 128 or sum(map(len, values)) > 200_000:
            raise HTTPException(422, "Processor embedding inputs exceed the supported limits")
        processor_claim(request, "embedding", payload.model, True)
        vectors = provider.embed(payload.model, values)
        return {"object": "list", "model": payload.model, "data": [
            {"index": i, "object": "embedding", "embedding": vector} for i, vector in enumerate(vectors)]}

    @app.post("/api/admin/intake/preview")
    def intake_preview(payload: IntakePlan, account=Depends(require("admin"))):
        from osii.server.intake import plan
        return plan(store, settings, payload.paths, operation=payload.operation, embed=payload.embed or payload.operation == "embed",
            synthesizer_name=payload.synthesizer_name, enricher_name=payload.enricher_name,
            synthesizer_config=payload.synthesizer_config, enricher_config=payload.enricher_config, expert_context=payload.expert_context)

    @app.post("/api/admin/intake/stage")
    def intake_stage(payload: IntakePlan, account=Depends(require("admin"))):
        reviewed = intake_preview(payload, account)
        jid = store.enqueue("plan", reviewed, status="staged")
        store.record("processing_staged", account["id"], jid)
        from osii.server.intake import public_run
        return public_run(store.job(jid))

    @app.post("/api/admin/runs/{jid}/{action}")
    def intake_control(jid: str, action: Literal["start", "pause", "resume", "cancel", "retry"], account=Depends(require("admin"))):
        from osii.server.intake import configuration_stamp, public_run
        try:
            result = store.control_job(jid, action, lambda: configuration_stamp(store, settings))
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        store.record("processing_" + action, account["id"], jid)
        return public_run(result)

    @app.get("/api/admin/runs")
    def processing_activity(account=Depends(require("admin"))):
        from osii.server.intake import public_run
        from datetime import datetime, timezone, timedelta
        last_seen = store.setting("worker_status", {}).get("last_seen")
        available = bool(last_seen and datetime.fromisoformat(last_seen) > datetime.now(timezone.utc) - timedelta(seconds=45))
        return {"runs": [public_run(job) for job in store.job_records()], "worker": {"available": available}}

    @app.get("/api/objects/{file_id}/extractions")
    def extraction_history(file_id: str, account=Depends(require())):
        document(file_id, account)
        records = store.extraction_records(file_id)
        return {"items": [{**row, "primary": i == 0} for i, row in enumerate(records)]}

    @app.post("/api/admin/intake")
    def intake(payload: Ingest | None = None, account=Depends(require("curator"))):
        selection = store.setting("source", {"directory": "."})
        resolve_directory(settings.source_root, selection["directory"])
        jid = store.enqueue("ingest", {**(payload.model_dump() if payload else {}), "source_directory": selection["directory"]})
        store.record("ingestion_requested", account["id"], jid)
        return {"id": jid, "status": "queued", **selection}

    @app.get("/api/runs")
    def runs(account=Depends(require("curator"))):
        return {"runs": store.job_records(), "source_directory": store.setting("source", {"directory": "."})["directory"]}

    return app
