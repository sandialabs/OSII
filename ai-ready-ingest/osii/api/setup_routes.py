"""Human-facing setup summary and safe proxy to the local capability supervisor."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request
import requests

from osii.api.model_provider_routes import _load, _public, _with_runtime_defaults
from osii.domain.processing.capability_readiness import intake_capability_readiness


router = APIRouter(prefix="/api/admin", tags=["setup"])


def _supervisor_request(method: str, path: str) -> dict[str, Any]:
    base_url = os.getenv("OSII_SERVICE_SUPERVISOR_URL", "").rstrip("/")
    token = os.getenv("OSII_SERVICE_SUPERVISOR_TOKEN", "")
    if not base_url or not token:
        raise HTTPException(status_code=503, detail="Local service control is not available in this deployment")
    try:
        response = requests.request(
            method,
            f"{base_url}{path}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=185 if method == "POST" else 8,
        )
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(status_code=503, detail=f"Local service supervisor is unavailable: {exc}") from exc
    if not response.ok:
        raise HTTPException(status_code=response.status_code, detail=payload.get("detail", "Service action failed"))
    return payload


def _services() -> tuple[bool, list[dict[str, Any]]]:
    try:
        return True, list(_supervisor_request("GET", "/services").get("services", []))
    except HTTPException:
        return False, []


def _health_only_services(readiness: dict[str, Any]) -> list[dict[str, Any]]:
    lookup = {
        str(item.get("id")): item
        for group in ("extractors", "synthesizers", "embedders", "enrichers")
        for item in readiness.get(group, [])
    }
    definitions = (
        ("tika", "Apache Tika", "Adds broad document-format text extraction."),
        ("local.native-text", "Python document extractor", "Reads text-layer PDFs, Office files, and text formats."),
        ("local.extractive-preview", "Source excerpt preview", "Creates a cited preview without an AI model."),
        ("local.hashing", "Lexical hashing compatibility embedder", "Optional lexical vectors; BM25 works without it."),
        ("local.stats-keywords", "Statistics and keywords enricher", "Creates local statistics and keyword artifacts."),
    )
    result = []
    for capability_id, title, description in definitions:
        item = lookup.get(capability_id)
        if item is None:
            continue
        result.append({
            "id": capability_id.split(".")[-1],
            "display_name": title,
            "description": description,
            "status": "external" if item.get("available") else "stopped",
            "ownership": "external" if item.get("available") else "none",
            "url": item.get("base_url") or "",
            "health_path": "/health",
            "can_start": False,
            "can_stop": False,
            "can_restart": False,
            "prerequisite": "Managed by this deployment." if not item.get("available") else None,
            "detail": item.get("detail"),
        })
    return result


def _selected_method(readiness: dict[str, Any], kind: str) -> dict[str, Any]:
    collection_name = f"{kind}s" if kind != "enricher" else "enrichers"
    selected = str(readiness["defaults"].get(kind) or "")
    for item in readiness.get(collection_name, []):
        aliases = item.get("aliases") or []
        if item.get("id") == selected or selected in aliases:
            if not item.get("available") and kind == "synthesizer":
                baseline = next(
                    (
                        candidate
                        for candidate in readiness.get("synthesizers", [])
                        if candidate.get("id") == "local.extractive-preview"
                        and candidate.get("available")
                    ),
                    None,
                )
                if baseline is not None:
                    item = baseline
                    selected = "local.extractive-preview"
            if not item.get("available") and kind == "embedder":
                return {
                    "id": "bm25",
                    "display_name": "Off — BM25 search remains available",
                    "available": False,
                    "description": "Connect an embedding model for semantic search. BM25 remains the keyword-search fallback.",
                    "model": None,
                }
            return {
                "id": selected,
                "display_name": item.get("display_name") or selected,
                "available": bool(item.get("available")),
                "description": item.get("description") or "",
                "model": item.get("model"),
            }
    labels = {
        "extractor": "Python PDF and Office text extractor",
        "synthesizer": "Source excerpt preview — no AI",
        "embedder": "Off — BM25 search remains available",
        "enricher": "Statistics and keywords",
    }
    return {
        "id": selected,
        "display_name": labels[kind],
        "available": kind != "embedder",
        "description": "",
        "model": None,
    }


@router.get("/setup")
def setup_summary(request: Request):
    osii_root = request.app.state.osii_root.resolve()
    readiness = intake_capability_readiness(osii_root)
    service_control_available, services = _services()
    if not service_control_available:
        services = _health_only_services(readiness)
    records = sorted(
        _with_runtime_defaults(_load(osii_root)),
        key=lambda item: (int(item.get("priority", 100)), item.get("id", "")),
    )
    providers = [_public(item) for item in records]
    extraction_ready = any(item.get("available") for item in readiness["extractors"])
    ai_ready = any(
        item.get("available") and not str(item.get("id", "")).startswith("local.")
        for key in ("synthesizers", "embedders")
        for item in readiness[key]
    )
    if not extraction_ready:
        overall = "action_required"
        headline = "Document reading needs attention"
    elif ai_ready:
        overall = "ready"
        headline = "Ready for Intake"
    else:
        overall = "ready_optional"
        headline = "Connect AI to complete setup"
    return {
        "overall_status": overall,
        "headline": headline,
        "extraction_ready": extraction_ready,
        "ai_ready": ai_ready,
        "methods": {
            kind: _selected_method(readiness, kind)
            for kind in ("extractor", "synthesizer", "embedder", "enricher")
        },
        "providers": providers,
        "services": services,
        "service_control_available": service_control_available,
        "readiness": readiness,
    }


@router.get("/services")
def list_services():
    return _supervisor_request("GET", "/services")


@router.post("/services/{service_id}/{action}")
def control_service(service_id: str, action: str):
    if action not in {"start", "stop", "restart"}:
        raise HTTPException(status_code=404, detail="Unknown service action")
    return _supervisor_request("POST", f"/services/{service_id}/{action}")


@router.get("/services/{service_id}/logs")
def service_logs(service_id: str):
    return _supervisor_request("GET", f"/services/{service_id}/logs")
