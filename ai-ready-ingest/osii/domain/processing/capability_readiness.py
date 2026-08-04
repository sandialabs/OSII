from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests
import tomllib
from osii.indexing.common import embeddings_meta_path
from osii.domain.catalog_db import list_semantic_indexes

from osii.processors.remote import discover_remote_processors


def _service_probe(url: str, *, timeout: float = 3.0) -> tuple[bool, str]:
    try:
        response = requests.get(url, timeout=timeout)
        if response.ok:
            return True, f"Connected ({response.status_code})"
        return False, f"HTTP {response.status_code}: {response.text[:160]}"
    except requests.RequestException as exc:
        return False, str(exc)


def _embedding_probe() -> dict[str, Any]:
    selected = os.getenv("OSII_DEFAULT_EMBEDDER", "").strip()
    if selected:
        for descriptor in discover_remote_processors(include_errors=True):
            if descriptor.get("name") != selected:
                continue
            available = not descriptor.get("error")
            model = selected
            dimensions = None
            provider = selected
            detail = "Descriptor validated."
            if available:
                try:
                    probe = requests.post(
                        f"{descriptor['base_url']}/v1/embed",
                        json={"request_id": "readiness", "inputs": [{"id": "probe", "text": "OSII readiness probe"}]},
                        timeout=8,
                    )
                    probe.raise_for_status()
                    payload = probe.json()
                    model = payload["model"]
                    provider = payload["processor"]["name"]
                    dimensions = payload["vectors"][0]["dimensions"]
                    detail = f"Descriptor and {dimensions}-dimensional vector validated."
                except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
                    available = False
                    detail = f"Embedding operation test failed: {exc}"
            return {
                "id": selected,
                "display_name": descriptor.get("display_name", selected),
                "kind": "embedder",
                "available": available,
                "detail": detail if available else descriptor.get("error", detail),
                "model": model,
                "provider": provider,
                "dimensions": dimensions,
                "base_url": descriptor.get("base_url"),
                "bundled": selected.startswith("local."),
                "lexical": selected == "local.hashing",
            }
    base_url = (
        os.getenv("OSII_EMBEDDING_BASE_URL")
        or os.getenv("OSII_MODEL_BASE_URL")
        or ""
    ).strip().rstrip("/")
    model = os.getenv(
        "EMBEDDING_MODEL",
        "osii-local-hashing-v1",
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
            "id": "native_text",
            "aliases": ["native_text"],
            "display_name": "Native Python Text Extractor",
            "description": (
                "Container-free extraction for text-layer PDFs, modern Office "
                "documents, and common text formats."
            ),
            "available": True,
            "detail": "Bundled in the OSII Python package.",
            "bundled": True,
        },
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

    remote_by_kind: dict[str, list[dict[str, Any]]] = {kind: [] for kind in ("extractor", "synthesizer", "embedder", "enricher")}
    for descriptor in discover_remote_processors(include_errors=True):
        kind = descriptor.get("kind")
        if kind not in remote_by_kind:
            continue
        remote_by_kind[kind].append({
            "id": descriptor.get("name", descriptor.get("base_url")),
            "display_name": descriptor.get("display_name", descriptor.get("base_url")),
            "description": descriptor.get("description", "Processor API service"),
            "kind": kind,
            "available": not descriptor.get("error"),
            "detail": "Descriptor validated." if not descriptor.get("error") else descriptor["error"],
            "base_url": descriptor.get("base_url"),
            "bundled": str(descriptor.get("name", "")).startswith("local."),
            "descriptor": descriptor if not descriptor.get("error") else None,
        })

    embedding = embedding_readiness()
    index_metadata: dict[str, Any] = {}
    try:
        index_metadata = tomllib.loads(embeddings_meta_path(osii_root).read_text(encoding="utf-8")).get("embeddings", {})
    except (OSError, tomllib.TOMLDecodeError):
        pass
    if index_metadata and embedding.get("available"):
        expected_model = embedding.get("model")
        embedding["index_compatible"] = (
            index_metadata.get("model") == expected_model
            and index_metadata.get("provider") == embedding.get("provider")
            and index_metadata.get("dimension") == embedding.get("dimensions")
        )
        embedding["index_rebuild_required"] = not embedding["index_compatible"]
        embedding["indexed_model"] = index_metadata.get("model")
    elif embedding.get("available"):
        embedding["index_compatible"] = False
        embedding["index_rebuild_required"] = True

    return {
        "defaults": {
            "extractor": os.getenv("OSII_DEFAULT_EXTRACTOR", "native_text"),
            "synthesizer": os.getenv("OSII_DEFAULT_SYNTHESIZER", "firstN"),
            "embedder": os.getenv("OSII_DEFAULT_EMBEDDER", ""),
            "enricher": os.getenv("OSII_DEFAULT_ENRICHER", "stats_keywords"),
        },
        "extractors": remote_by_kind["extractor"] + extractors,
        "synthesizers": remote_by_kind["synthesizer"] + [
            {
                "id": "firstN",
                "display_name": "Local text preview",
                "kind": "synthesizer",
                "available": True,
                "detail": "Bundled deterministic synthesizer; no model service required.",
                "bundled": True,
            }
        ],
        "embedders": [embedding] if embedding.get("id") else remote_by_kind["embedder"],
        "enrichers": remote_by_kind["enricher"] + [
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
        "semantic_indexes": list_semantic_indexes(osii_root),
    }
