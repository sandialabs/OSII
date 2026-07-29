from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

import requests


def create_shirty_client() -> Any:
    """Load the optional corporate model client only when a connected feature runs."""
    try:
        from shirty.client import ShirtyClient
    except ImportError as exc:
        raise RuntimeError(
            "This processor requires the optional Shirty model client. "
            "Install OSII with the 'connected' extra in an environment where "
            "the corporate package is available, or select a local processor."
        ) from exc
    return ShirtyClient()


class LocalEmbeddingClient:
    """Small OpenAI-compatible client for OSII's bundled embedding service."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.embeddings = self

    def create(self, *, model: str, input: list[str]):
        try:
            response = requests.post(
                f"{self.base_url}/embeddings",
                json={"model": model, "input": input, "encoding_format": "float"},
                timeout=120,
            )
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data", [])
            if not isinstance(data, list) or len(data) != len(input):
                raise RuntimeError("Embedding service returned an invalid response.")
            return SimpleNamespace(
                data=[SimpleNamespace(embedding=row["embedding"]) for row in data]
            )
        except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(f"Local embedding service request failed: {exc}") from exc


def create_embedding_client() -> Any:
    """Use the bundled service when configured, otherwise use an optional client."""
    base_url = os.getenv("OSII_EMBEDDING_BASE_URL", "").strip()
    if base_url:
        return LocalEmbeddingClient(base_url)
    return create_shirty_client()
