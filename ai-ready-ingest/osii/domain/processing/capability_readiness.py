from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests


def _service_probe(url: str, *, timeout: float = 3.0) -> tuple[bool, str]:
    try:
        response = requests.get(url, timeout=timeout)
        if response.ok:
            return True, f"Connected ({response.status_code})"
        return False, f"HTTP {response.status_code}: {response.text[:160]}"
    except requests.RequestException as exc:
        return False, str(exc)


def _embedding_probe() -> dict[str, Any]:
    base_url = (
        os.getenv("OSII_EMBEDDING_BASE_URL")
        or os.getenv("OSII_MODEL_BASE_URL")
        or ""
    ).strip().rstrip("/")
    model = os.getenv(
        "EMBEDDING_MODEL",
        "jinaai/jina-embeddings-v2-base-en",
    ).strip()
    if not base_url:
        return {
            "id": "embedding",
            "display_name": "Search embeddings",
            "kind": "embedder",
            "available": False,
            "detail": "No embedding endpoint is configured.",
            "model": model,
            "bundled": False,
        }

    try:
        response = requests.post(
            f"{base_url}/embeddings",
            json={
                "model": model,
                "input": ["OSII capability readiness probe"],
                "encoding_format": "float",
            },
            timeout=8,
        )
        response.raise_for_status()
        rows = response.json().get("data")
        available = bool(
            isinstance(rows, list)
            and rows
            and isinstance(rows[0].get("embedding"), list)
            and rows[0]["embedding"]
        )
        detail = (
            f"Connected to {base_url}"
            if available
            else "The endpoint responded without a usable embedding vector."
        )
    except (requests.RequestException, ValueError, AttributeError) as exc:
        available = False
        detail = f"Embedding test failed: {exc}"

    return {
        "id": "embedding",
        "display_name": "Search embeddings",
        "kind": "embedder",
        "available": available,
        "detail": detail,
        "model": model,
        "base_url": base_url,
        "bundled": False,
    }


def embedding_readiness() -> dict[str, Any]:
    """Return a tested view of the configured embedding capability."""

    return _embedding_probe()


def _registered_endpoints(osii_root: Path) -> list[dict[str, Any]]:
    path = osii_root / "state" / "processor_endpoints.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def intake_capability_readiness(osii_root: Path) -> dict[str, Any]:
    tika_url = os.getenv("TIKA_URL", "http://localhost:9998").rstrip("/")
    tika_available, tika_detail = _service_probe(f"{tika_url}/version")

    tesseract_url = os.getenv(
        "OSII_TESSERACT_URL",
        "http://127.0.0.1:8080",
    ).rstrip("/")
    tesseract_available, tesseract_detail = _service_probe(
        f"{tesseract_url}/health"
    )

    nemotron_url = os.getenv("NEMOTRON_BASE_URL", "").strip().rstrip("/")
    if nemotron_url:
        nemotron_available, nemotron_detail = _service_probe(
            f"{nemotron_url}/v1/models"
        )
    else:
        nemotron_available = False
        nemotron_detail = "NEMOTRON_BASE_URL is not configured."

    extractors = [
        {
            "id": "tika",
            "aliases": ["tika", "tika_catchall"],
            "display_name": "Apache Tika",
            "description": "General text extraction for PDFs, Office files, and catch-all formats.",
            "available": tika_available,
            "detail": tika_detail,
            "bundled": True,
        },
        {
            "id": "osii_tesseract",
            "aliases": ["osii_tesseract"],
            "display_name": "OSII Tesseract OCR",
            "description": "Page-grounded OCR for scanned PDFs and supported documents.",
            "available": tesseract_available,
            "detail": tesseract_detail,
            "bundled": True,
        },
        {
            "id": "pdf_default",
            "aliases": [
                "pdf_default",
                "banyan",
                "banyan_ingest",
                "banyan-extract",
            ],
            "display_name": "Nemotron PDF parser",
            "description": "Model-backed page parsing for PDFs.",
            "available": nemotron_available,
            "detail": nemotron_detail,
            "bundled": False,
        },
    ]

    external = []
    for endpoint in _registered_endpoints(osii_root):
        if not endpoint.get("enabled"):
            continue
        base_url = str(endpoint.get("base_url") or "").rstrip("/")
        available, detail = _service_probe(f"{base_url}/health")
        external.append(
            {
                **endpoint,
                "available": available,
                "detail": detail,
                "bundled": False,
            }
        )

    return {
        "extractors": extractors,
        "synthesizers": [
            {
                "id": "firstN",
                "display_name": "Local text preview",
                "kind": "synthesizer",
                "available": True,
                "detail": "Bundled deterministic synthesizer; no model service required.",
                "bundled": True,
            }
        ],
        "embedders": [embedding_readiness()],
        "enrichers": [
            {
                "id": "stats_keywords",
                "display_name": "Statistics and keywords",
                "kind": "enricher",
                "available": True,
                "detail": "Bundled locally; run after intake from a file or collection.",
                "bundled": True,
            },
            {
                "id": "llm_wiki_stub",
                "display_name": "LLM wiki artifact template",
                "kind": "enricher",
                "available": True,
                "detail": "Bundled artifact example; run after intake.",
                "bundled": True,
            },
        ],
        "external": external,
    }
