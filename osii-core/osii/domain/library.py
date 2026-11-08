"""Shared-library operations; independent of HTTP and SQL implementations."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from osii.rag.prompts import build_system_prompt, build_user_prompt
from osii.search.engine import RetrievalEngine
from osii.model_provider import ModelProvider, ProviderError


class LibraryStore(Protocol):
    def snapshot(self) -> tuple[int, list[dict], list[dict]]: ...
    def configuration(self) -> dict: ...
    def collection_records(self, user_id: str | None = None) -> list[dict]: ...


class Library:
    def __init__(self, store: LibraryStore, provider: ModelProvider):
        self.store, self.provider = store, provider
        self.retrieval = RetrievalEngine()

    def scoped(self, scope: dict, user_id: str | None = None):
        revision, documents, rows = self.store.snapshot()
        scoped_documents = scope_documents(documents, scope, self.store.collection_records(user_id))
        allowed = {d['file_id'] for d in scoped_documents}
        rows = [row for row in rows if row["file_id"] in allowed]
        return revision, [d for d in documents if d["file_id"] in allowed], rows

    def search(self, query: str, mode: str, top_k: int, scope: dict, user_id: str | None = None) -> dict:
        revision, documents, rows = self.scoped(scope, user_id)
        configuration = self.store.configuration()
        vector, warning = None, None
        embedding_model = configuration.get("embedding_model", "")
        if mode != "lexical" and embedding_model and any(r.get("embedding_model") == embedding_model for r in rows):
            try:
                vector = self.provider.embed(embedding_model, [query])[0]
            except ProviderError:
                warning = "Semantic provider unavailable; keyword and OCR-tolerant retrieval used."
        if mode == "semantic" and vector is None:
            raise ValueError("Semantic search requires a working embedding model and a compatible indexed corpus")
        results, channels = self.retrieval.search(rows, query, revision=revision, mode=mode,
            top_k=top_k, query_vector=vector, embedding_model=embedding_model)
        for row in results:
            row.pop("embedding", None)
        return {"query": query, "mode": mode, "retrieval_mode_used": "hybrid" if "semantic" in channels and len(channels) > 1 else "semantic" if channels == ["semantic"] else "lexical",
            "results": results, "channels_used": channels, "corpus_revision": revision, "warning": warning}

    def chat(self, query: str, scope: dict, history: list[dict], user_id: str | None = None) -> dict:
        found = self.search(query, "hybrid", 8, scope, user_id)
        evidence = found["results"]
        citations = [{k: row.get(k) for k in ("file_id", "filename", "source_relpath", "snippet", "chunk_id", "char_start", "char_end", "source_origin")} for row in evidence]
        model = self.store.configuration().get("chat_model", "")
        answer, usage, fallback = "", {}, False
        if evidence and model:
            try:
                answer, usage = self.provider.chat(model, [{"role": "system", "content": build_system_prompt()},
                    {"role": "user", "content": build_user_prompt(query=query, scope=scope, history=history, evidence=evidence)}])
            except ProviderError:
                fallback = True
        if not answer:
            fallback = True
            answer = "I could not find grounded text in this scope to answer the question." if not evidence else (
                "Source excerpts (extractive fallback):\n\n" + "\n\n".join(f"{row['snippet']} [{row['filename']}]" for row in evidence[:5]))
        return {"answer": answer, "citations": citations, "provider": "extractive" if fallback else "openai",
            "model": model if not fallback else None, "fallback_used": fallback,
            "retrieval_mode": found["retrieval_mode_used"], "channels_used": found["channels_used"],
            "corpus_revision": found["corpus_revision"], "usage": usage}


def scope_documents(documents: list[dict], scope: dict, collection_records: list[dict]) -> list[dict]:
    kind = scope.get("scope_type", "root")
    allowed = {document["file_id"] for document in documents}
    if kind == "object":
        allowed &= {scope.get("file_id")}
    elif kind == "folder":
        prefix = scope.get("folder_id", "").strip("/")
        if prefix not in {"", "."}:
            allowed = {d["file_id"] for d in documents if str(Path(d["source_relpath"]).parent) == prefix or d["source_relpath"].startswith(prefix + "/")}
    elif kind == "collection":
        collection = next((c for c in collection_records if c["id"] == scope.get("collection_id")), None)
        if not collection:
            raise ValueError("Collection not found")
        allowed &= set(collection["members"])
    elif kind != "root":
        raise ValueError("Unsupported scope")
    return [doc for doc in documents if doc["file_id"] in allowed]
