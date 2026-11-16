"""Suggestion HTTP composition; adapters read bounded saved data, never originals."""

from __future__ import annotations
import hashlib
import json
from threading import Lock
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from osii.domain.collection_suggestions import (
    VERSION,
    SuggestionModelError,
    topic_proposals,
    guided_proposals,
)
from osii.api.file_display_routes import postgres_previews, sidecar_previews


class SuggestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=1, max_length=2000)


def register_collection_suggestion_routes(
    app: FastAPI, *, store=None, connections=None, provider=None
) -> None:
    if store is not None:
        from osii.server.auth import require

        guard = require()
    else:

        def guard():
            return None

    cache_lock = Lock()

    def library(request):
        return store or getattr(request.app.state, "postgres_library", None)

    def chat(request):
        if store is not None:
            model = store.configuration().get("chat_model", "")
            return bool(model and connections.endpoints()["chat"].base_url), model
        from osii.rag.config import get_chat_settings

        service = library(request)
        root = (
            service.backend.root
            if service is not None
            else request.app.state.osii_root.resolve()
        )
        settings = get_chat_settings(root)
        kind = settings.chat_provider_chain[0]
        model = (
            settings.ollama_chat_model
            if kind == "ollama"
            else settings.openai_chat_model or settings.chat_model
        )
        return bool(kind in {"ollama", "openai"} and model), model

    def load(request):
        service = library(request)
        if service is not None:
            from sqlalchemy import text

            if store is not None:
                with store.topic_snapshot() as (revision, headers, _):
                    documents = headers
            else:
                with service.engine.connect() as connection:
                    documents = [
                        dict(row)
                        for row in connection.execute(
                            text(
                                "SELECT file_id,filename,source_relpath FROM documents WHERE active ORDER BY file_id"
                            )
                        ).mappings()
                    ]
                    revision = (
                        connection.execute(
                            text("SELECT revision FROM datasets WHERE id='shared'")
                        ).scalar()
                        or 0
                    )
            if store is not None:
                model = store.configuration().get("embedding_model", "")
            else:
                from osii.domain.model_provider_config import selected_model

                model = selected_model("embedder", osii_root=service.backend.root)
            epoch = [revision, model]
        else:
            from osii.domain.read.sidecar import SidecarLibraryReader

            reader = SidecarLibraryReader(request.app.state.osii_root.resolve())
            documents = []
            cursor = None
            while True:
                page = reader.list_documents(limit=500, cursor=cursor)
                documents.extend(
                    {
                        "file_id": row.file_id,
                        "filename": row.filename,
                        "source_relpath": row.source_relpath,
                    }
                    for row in page.items
                )
                cursor = page.next_cursor
                if not cursor:
                    break
            from osii.domain.read.synthesis import get_suggested_metadata

            for row in documents:
                row.update(
                    get_suggested_metadata(
                        request.app.state.osii_root.resolve(), row["file_id"]
                    )
                )
            try:
                from osii.domain.services.topic_cache import context

                epoch = [
                    context(
                        request.app.state.osii_root.resolve(),
                        {"scope_type": "root"},
                        None,
                    )[0]
                ]
            except ValueError:
                epoch = ["no-compatible-index"]
        for start in range(0, len(documents), 48):
            batch = documents[start : start + 48]
            ids = [row["file_id"] for row in batch]
            previews = (
                postgres_previews(service.engine, ids)
                if service is not None
                else sidecar_previews(request.app.state.osii_root.resolve(), ids)
            )
            for row in batch:
                row.update(previews.get(row["file_id"], {}))
        documents.sort(key=lambda row: row["file_id"])
        identity = hashlib.sha256(
            json.dumps(
                [VERSION, epoch, documents], sort_keys=True, default=str
            ).encode()
        ).hexdigest()
        return documents, identity

    def vector_space(request, documents):
        service = library(request)
        if service is not None:
            from sqlalchemy import text

            if store is not None:
                model = store.configuration().get("embedding_model", "")
            else:
                # Local PostgreSQL's embedding selection lives in its existing configuration.
                from osii.domain.model_provider_config import selected_model

                model = selected_model("embedder", osii_root=service.backend.root)
            if not model:
                return [], None
            from osii.domain.topics import document_space

            with service.engine.connect().execution_options(
                stream_results=True, max_row_buffer=16
            ) as connection:
                result = connection.execute(
                    text("""
                    SELECT c.file_id,c.embedding,c.embedding_model FROM chunks c
                    JOIN documents d ON d.file_id=c.file_id WHERE d.active
                        AND c.embedding_model=:model
                        AND NOT COALESCE((d.metadata->'stale'->>'embeddings')::boolean,false)
                        AND COALESCE(d.metadata->'embedding_identity'->>'provider','')<>'local.hashing'
                """),
                    {"model": model},
                )
                try:
                    docs, vectors, _, _ = document_space(
                        documents, result.mappings(), model, 0
                    )
                finally:
                    result.close()
            return docs, vectors
        from osii.domain.services.topics import load_document_space

        space = load_document_space(
            request.app.state.osii_root.resolve(), {"scope_type": "root"}
        )
        return (
            (space.documents, space.vectors)
            if space.index.get("semantic")
            else ([], None)
        )

    def cached(request, identity):
        service = library(request)
        if service is not None:
            value = service.setting("collection_suggestions", {})
        else:
            path = (
                request.app.state.osii_root.resolve()
                / "cache"
                / "collection-suggestions.json"
            )
            try:
                value = (
                    json.loads(path.read_text()) if path.stat().st_size < 500000 else {}
                )
            except (OSError, ValueError):
                value = {}
        return value.get("result") if value.get("identity") == identity else None

    def save_cache(request, identity, result):
        value = {"identity": identity, "result": result}
        service = library(request)
        if service is not None:
            if store is not None:
                store.save_setting("collection_suggestions", value)
            else:
                service.set_setting("collection_suggestions", value)
        else:
            from osii.domain.storage.atomic import atomic_write_text

            try:
                atomic_write_text(
                    request.app.state.osii_root.resolve()
                    / "cache"
                    / "collection-suggestions.json",
                    json.dumps(value),
                )
            except OSError:
                pass

    def build(request, documents):
        try:
            semantic_documents, vectors = vector_space(request, documents)
        except ValueError:
            semantic_documents, vectors = [], None
        return topic_proposals(documents, semantic_documents, vectors, limit=12)

    def envelope(request, documents, items, *, guided=False, candidate_count=None):
        enabled, model = chat(request)
        return {
            "suggestions": items,
            "considered_documents": len(documents),
            "grouped_documents": len(
                {fid for item in items for fid in item["file_ids"]}
            ),
            "candidate_documents": candidate_count
            if candidate_count is not None
            else len(documents),
            "can_prompt": enabled,
            "chat_model": model or None,
            "guided": guided,
            "algorithm": VERSION,
        }

    @app.get("/api/collection-suggestions")
    def suggestions(request: Request, actor=Depends(guard)):
        documents, identity = load(request)
        result = cached(request, identity)
        if result is None:
            with cache_lock:
                result = cached(request, identity)
                if result is None:
                    result = build(request, documents)[:6]
                    save_cache(request, identity, result)
        return envelope(request, documents, result)

    @app.post("/api/collection-suggestions")
    def prompted(request: Request, payload: SuggestionRequest, actor=Depends(guard)):
        if not payload.prompt.strip():
            raise HTTPException(422, "Describe the collections you want")
        enabled, model = chat(request)
        if not enabled:
            raise HTTPException(
                409, "Configure a chat model in Setup for prompt-guided suggestions"
            )
        if store is not None:
            if not store.login_allowed(
                "collections:" + actor["id"], failed=True, maximum=12
            ) or not store.login_allowed("collections:global", failed=True, maximum=60):
                raise HTTPException(
                    429, "Suggestion limit reached; try again in 15 minutes"
                )
        documents, _ = load(request)
        if len(documents) < 2:
            return envelope(
                request, documents, [], guided=True, candidate_count=len(documents)
            )
        topics = build(request, documents)

        def complete(messages):
            if store is not None:
                return provider.chat(model, messages, max_tokens=4000, temperature=0)[0]
            from osii.rag.config import get_chat_settings
            from osii.rag.generation import run_messages

            service = library(request)
            root = (
                service.backend.root
                if service is not None
                else request.app.state.osii_root.resolve()
            )
            settings = get_chat_settings(root)
            return run_messages(
                provider=settings.chat_provider_chain[0],
                settings=settings,
                model=model,
                messages=messages,
                max_tokens=4000,
            )

        try:
            items, count = guided_proposals(
                documents, payload.prompt.strip(), complete, topics
            )
        except SuggestionModelError as exc:
            raise HTTPException(502, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                502,
                "The configured chat model could not suggest collections. Try again; saved collections are unchanged.",
            ) from exc
        return envelope(request, documents, items, guided=True, candidate_count=count)
