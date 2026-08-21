from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path
from typing import Any

import requests
from osii.domain.catalog_db import list_semantic_indexes
from osii.domain.model_provider_config import processor_model, selected_processor
from osii.enrichment.llm_wiki import LlmWikiEnricher
from osii.indexing.common import embeddings_meta_path
from osii.processors.remote import discover_remote_processors


def _service_probe(url: str, *, timeout: float = 3.0) -> tuple[bool, str]:
    try:
        response = requests.get(url, timeout=timeout)
        if response.ok:
            return True, f"Connected ({response.status_code})"
        return False, f"HTTP {response.status_code}: {response.text[:160]}"
    except requests.RequestException as exc:
        return False, str(exc)


def _model_name_matches(installed: str, requested: str) -> bool:
    return (
        installed == requested
        or installed == f"{requested}:latest"
        or requested == f"{installed}:latest"
    )


def _ollama_model_status(model: str) -> tuple[bool, str]:
    """Distinguish a running OSII adapter from a usable Ollama model."""

    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=(3, 8))
        response.raise_for_status()
        rows = response.json().get("models") or []
        names = [
            str(item.get("model") or item.get("name") or "")
            for item in rows
            if isinstance(item, dict)
        ]
    except (requests.RequestException, ValueError, AttributeError) as exc:
        return False, (
            "OSII's Ollama adapter is running, but the separately installed Ollama "
            f"application is not reachable at {base_url}: {exc}"
        )
    if not any(_model_name_matches(name, model) for name in names):
        return False, (
            f"Ollama is running, but model '{model}' is not installed. "
            "Download it from Tools → AI models."
        )
    return True, f"Ollama is running and model '{model}' is installed."


def _embedding_probe(osii_root: Path | None = None) -> dict[str, Any]:
    selected = selected_processor("embedder", osii_root=osii_root)
    if selected:
        for descriptor in discover_remote_processors(include_errors=True):
            if descriptor.get("name") != selected:
                continue
            available = not descriptor.get("error")
            model = processor_model(selected, "embedder", osii_root=osii_root) or selected
            dimensions = None
            provider = selected
            detail = "Descriptor validated."
            if available and selected.startswith("ollama."):
                available, detail = _ollama_model_status(model)
            if available:
                try:
                    probe = requests.post(
                        f"{descriptor['base_url']}/v1/embed",
                        json={
                            "request_id": "readiness",
                            "inputs": [{"id": "probe", "text": "OSII readiness probe"}],
                        },
                        timeout=8,
                    )
                    probe.raise_for_status()
                    payload = probe.json()
                    model = payload["model"]
                    provider = payload["processor"]["name"]
                    dimensions = payload["vectors"][0]["dimensions"]
                    detail = (
                        f"Descriptor and {dimensions}-dimensional vector validated."
                    )
                except (
                    requests.RequestException,
                    ValueError,
                    KeyError,
                    IndexError,
                ) as exc:
                    available = False
                    detail = f"Embedding operation test failed: {exc}"
            display_name = descriptor.get("display_name", selected)
            if model and not selected.startswith("local."):
                display_name = f"{display_name} · {model}"
            return {
                "id": selected,
                "display_name": display_name,
                "description": descriptor.get("description", "Configured embedding processor."),
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
        (os.getenv("OSII_EMBEDDING_BASE_URL") or os.getenv("OSII_MODEL_BASE_URL") or "")
        .strip()
        .rstrip("/")
    )
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


def embedding_readiness(osii_root: Path | None = None) -> dict[str, Any]:
    """Return a tested view of the configured embedding capability."""

    return _embedding_probe(osii_root)


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
    tesseract_available, tesseract_detail = _service_probe(f"{tesseract_url}/health")

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
            "description": (
                "Optional OCR extraction for scanned PDFs. Tesseract reads page images and "
                "returns grounded text with page-region bounding boxes; start it separately."
            ),
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
            "config_schema": {
                "type": "object",
                "properties": {
                    "temperature": {
                        "type": "number",
                        "title": "VLM temperature",
                        "description": "Controls sampling for the Nemotron page parser.",
                        "minimum": 0,
                        "maximum": 2,
                        "default": 0,
                    },
                    "page_limit": {
                        "type": "integer",
                        "title": "Page limit",
                        "description": "Optional demo/debug limit. Leave blank to process every page.",
                        "minimum": 1,
                    },
                },
                "additionalProperties": False,
            },
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

    remote_by_kind: dict[str, list[dict[str, Any]]] = {
        kind: [] for kind in ("extractor", "synthesizer", "embedder", "enricher")
    }
    for descriptor in discover_remote_processors(include_errors=True):
        kind = descriptor.get("kind")
        if kind not in remote_by_kind:
            continue
        name = str(descriptor.get("name", descriptor.get("base_url")))
        model = (
            processor_model(name, kind, osii_root=osii_root)
            if kind in {"embedder", "synthesizer"}
            else ""
        )
        display_name = descriptor.get("display_name", descriptor.get("base_url"))
        if model:
            display_name = f"{display_name} · {model}"
        remote_by_kind[kind].append(
            {
                "id": name,
                "display_name": display_name,
                "description": descriptor.get("description", "Processor API service"),
                "kind": kind,
                "available": not descriptor.get("error"),
                "detail": "Descriptor validated."
                if not descriptor.get("error")
                else descriptor["error"],
                "base_url": descriptor.get("base_url"),
                "bundled": str(descriptor.get("name", "")).startswith("local."),
                "descriptor": descriptor if not descriptor.get("error") else None,
                **({"model": model} if model else {}),
            }
        )

    for kind in ("synthesizer", "embedder"):
        for item in remote_by_kind[kind]:
            if not str(item.get("id", "")).startswith("ollama."):
                continue
            model = str(item.get("model") or "").strip()
            if item.get("available") and model:
                item["available"], item["detail"] = _ollama_model_status(model)

    remote_extractor_ids = {item["id"] for item in remote_by_kind["extractor"]}
    if "local.native-text" not in remote_extractor_ids:
        extractors.insert(
            0,
            {
                "id": "native_text",
                "aliases": ["native_text", "local.native-text"],
                "display_name": "Python text-layer PDF and Office extractor",
                "description": (
                    "Reads text already stored inside PDFs, Office documents, and "
                    "common text formats. It does not perform OCR."
                ),
                "available": True,
                "detail": "Using the compatibility implementation in OSII core.",
                "bundled": True,
            },
        )

    synthesizers = list(remote_by_kind["synthesizer"])

    embedding = embedding_readiness(osii_root)
    index_metadata: dict[str, Any] = {}
    try:
        index_metadata = tomllib.loads(
            embeddings_meta_path(osii_root).read_text(encoding="utf-8")
        ).get("embeddings", {})
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

    embedders = [embedding] if embedding.get("id") else []
    known_embedder_ids = {item["id"] for item in embedders}
    embedders.extend(
        item
        for item in remote_by_kind["embedder"]
        if item["id"] not in known_embedder_ids
    )

    selected_synthesizer = selected_processor("synthesizer", osii_root=osii_root)
    selected_synthesizer_status = next(
        (
            item
            for item in remote_by_kind["synthesizer"]
            if item["id"] == selected_synthesizer
        ),
        None,
    )
    llm_wiki_available = bool(
        selected_synthesizer_status
        and selected_synthesizer_status.get("available")
        and selected_synthesizer
        not in {"local.extractive-preview", "firstN", "recursive"}
    )

    compatibility_enrichers = [
        {
            "id": "stats_keywords",
            "display_name": "Document statistics and frequent keywords",
            "kind": "enricher",
            "description": "Creates deterministic word counts and frequent-keyword artifacts from extracted text.",
            "available": True,
            "detail": "Python implementation inside OSII core; no model required.",
            "bundled": True,
        },
        {
            "id": "noun_adjective_ngrams",
            "display_name": "Noun/adjective phrase keywords",
            "kind": "enricher",
            "description": "Ranks recurring 2-, 3-, and 4-word noun/adjective phrases to provide a compact content snapshot.",
            "available": True,
            "detail": "Bundled local 2-, 3-, and 4-gram keyword snapshot; no model required.",
            "bundled": True,
        },
        {
            "id": "entity_candidates",
            "display_name": "Named entity candidates",
            "kind": "enricher",
            "description": "Finds grounded capitalized-name and acronym candidates without requiring a model download.",
            "available": True,
            "detail": "Bundled local capitalized-name and acronym candidates with grounded mentions.",
            "bundled": True,
        },
        {
            "id": "llm_wiki",
            "display_name": "LLM Wiki",
            "kind": "enricher",
            "description": "Uses the selected model-backed synthesizer to create a cited Markdown knowledge page for a document or collection.",
            "available": llm_wiki_available,
            "detail": (
                f"Uses the selected model-backed synthesizer: {selected_synthesizer}."
                if llm_wiki_available
                else "Select and test an Ollama or OpenAI-compatible synthesis model first."
            ),
            "bundled": False,
            "config_schema": LlmWikiEnricher.config_schema,
        },
    ]
    if any(
        item["id"] == "local.stats-keywords"
        for item in remote_by_kind["enricher"]
    ):
        compatibility_enrichers = [
            item for item in compatibility_enrichers if item["id"] != "stats_keywords"
        ]

    return {
        "defaults": {
            "extractor": os.getenv("OSII_DEFAULT_EXTRACTOR", "native_text"),
            "synthesizer": selected_processor("synthesizer", osii_root=osii_root),
            "embedder": selected_processor("embedder", osii_root=osii_root),
            "enricher": os.getenv("OSII_DEFAULT_ENRICHER", "stats_keywords"),
        },
        "extractors": remote_by_kind["extractor"] + extractors,
        "synthesizers": synthesizers,
        "embedders": embedders,
        "enrichers": remote_by_kind["enricher"] + compatibility_enrichers,
        "external": external,
        "semantic_indexes": list_semantic_indexes(osii_root),
    }
