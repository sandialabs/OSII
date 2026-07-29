from typing import Any

from app.osii_client import OsiiClient


def _is_embedding_unavailable_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return (
        "faiss index not found" in msg
        or "embeddings mapping not found" in msg
        or "embeddings metadata not found" in msg
        or "embedding" in msg and "not found" in msg
    )


def retrieve_with_fallback(
    *,
    osii_client: OsiiClient,
    query: str,
    top_k: int,
    scope: dict,
    preferred_mode: str = "hybrid",
    fallback_mode: str = "lexical",
) -> tuple[str, dict]:
    try:
        result = osii_client.search(
            query=query,
            mode=preferred_mode,
            top_k=top_k,
            scope=scope,
        )
        return preferred_mode, result
    except Exception as exc:
        if not _is_embedding_unavailable_error(exc):
            raise

    result = osii_client.search(
        query=query,
        mode=fallback_mode,
        top_k=top_k,
        scope=scope,
    )
    return fallback_mode, result