from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

import requests
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/admin/processors", tags=["processor-administration"])
VALID_KINDS = {"extractor", "synthesizer", "embedder", "enricher"}


def _config_path(osii_root: Path) -> Path:
    path = osii_root / "state" / "processor_endpoints.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load(osii_root: Path) -> list[dict[str, Any]]:
    path = _config_path(osii_root)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _save(osii_root: Path, endpoints: list[dict[str, Any]]) -> None:
    _config_path(osii_root).write_text(json.dumps(endpoints, indent=2), encoding="utf-8")


def _validate(payload: dict[str, Any], *, existing_ids: set[str] | None = None) -> dict[str, Any]:
    endpoint_id = str(payload.get("id") or "").strip().lower()
    if not endpoint_id:
        endpoint_id = f"endpoint-{uuid.uuid4().hex[:8]}"
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", endpoint_id):
        raise HTTPException(status_code=422, detail="id must contain lowercase letters, numbers, dots, underscores, or hyphens")
    if existing_ids is not None and endpoint_id in existing_ids:
        raise HTTPException(status_code=409, detail=f"endpoint id '{endpoint_id}' already exists")

    kind = str(payload.get("kind") or "").strip().lower()
    if kind not in VALID_KINDS:
        raise HTTPException(status_code=422, detail=f"kind must be one of {sorted(VALID_KINDS)}")
    base_url = str(payload.get("base_url") or "").strip().rstrip("/")
    if not base_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="base_url must start with http:// or https://")
    display_name = str(payload.get("display_name") or endpoint_id).strip()
    return {
        "id": endpoint_id,
        "display_name": display_name,
        "kind": kind,
        "base_url": base_url,
        "enabled": bool(payload.get("enabled", True)),
    }


def _headers(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


def _test_payload(kind: str) -> dict[str, Any]:
    if kind == "extractor":
        return {
            "api_version": "v1", "request_id": "health-test",
            "document": {"filename": "health.txt", "media_type": "text/plain", "content_base64": "aGVsbG8="},
        }
    if kind == "embedder":
        return {"api_version": "v1", "request_id": "health-test", "inputs": [{"id": "test", "text": "hello"}]}
    return {
        "api_version": "v1", "request_id": "health-test",
        "scope": {"scope_type": "object", "scope_id": "test", "documents": [{"filename": "health.txt", "text": "hello"}]},
    }


def _operation(kind: str) -> str:
    return {"extractor": "extract", "synthesizer": "synthesize", "embedder": "embed", "enricher": "enrich"}[kind]


def _health(endpoint: dict[str, Any], token: str | None = None) -> dict[str, Any]:
    try:
        response = requests.get(f"{endpoint['base_url']}/health", headers=_headers(token), timeout=5)
        return {"ok": response.ok, "status": response.status_code, "detail": response.text[:300]}
    except requests.RequestException as exc:
        return {"ok": False, "status": None, "detail": str(exc)}


@router.get("")
async def list_processor_endpoints(request: Request):
    return {"processors": _load(request.app.state.osii_root.resolve())}


@router.post("")
async def create_processor_endpoint(request: Request, payload: dict):
    osii_root = request.app.state.osii_root.resolve()
    endpoints = _load(osii_root)
    endpoint = _validate(payload, existing_ids={item["id"] for item in endpoints})
    endpoints.append(endpoint)
    _save(osii_root, endpoints)
    return {"processor": endpoint}


@router.put("/{endpoint_id}")
async def update_processor_endpoint(request: Request, endpoint_id: str, payload: dict):
    osii_root = request.app.state.osii_root.resolve()
    endpoints = _load(osii_root)
    for index, existing in enumerate(endpoints):
        if existing["id"] == endpoint_id:
            endpoint = _validate({**existing, **payload, "id": endpoint_id})
            endpoints[index] = endpoint
            _save(osii_root, endpoints)
            return {"processor": endpoint}
    raise HTTPException(status_code=404, detail="processor endpoint not found")


@router.delete("/{endpoint_id}")
async def delete_processor_endpoint(request: Request, endpoint_id: str):
    osii_root = request.app.state.osii_root.resolve()
    endpoints = _load(osii_root)
    updated = [item for item in endpoints if item["id"] != endpoint_id]
    if len(updated) == len(endpoints):
        raise HTTPException(status_code=404, detail="processor endpoint not found")
    _save(osii_root, updated)
    return {"deleted": endpoint_id}


@router.post("/{endpoint_id}/health")
async def health_processor_endpoint(request: Request, endpoint_id: str, payload: dict | None = None):
    endpoint = next((item for item in _load(request.app.state.osii_root.resolve()) if item["id"] == endpoint_id), None)
    if endpoint is None:
        raise HTTPException(status_code=404, detail="processor endpoint not found")
    return _health(endpoint, (payload or {}).get("token"))


@router.post("/{endpoint_id}/test")
async def test_processor_endpoint(request: Request, endpoint_id: str, payload: dict | None = None):
    endpoint = next((item for item in _load(request.app.state.osii_root.resolve()) if item["id"] == endpoint_id), None)
    if endpoint is None:
        raise HTTPException(status_code=404, detail="processor endpoint not found")
    token = (payload or {}).get("token")
    try:
        descriptor = requests.get(f"{endpoint['base_url']}/v1/descriptor", headers=_headers(token), timeout=5)
        descriptor.raise_for_status()
        data = descriptor.json()
        if data.get("kind") != endpoint["kind"]:
            raise HTTPException(status_code=422, detail=f"descriptor kind '{data.get('kind')}' does not match configured kind '{endpoint['kind']}'")
        response = requests.post(
            f"{endpoint['base_url']}/v1/{_operation(endpoint['kind'])}",
            headers={"Content-Type": "application/json", **_headers(token)},
            json=_test_payload(endpoint["kind"]),
            timeout=20,
        )
        return {"ok": response.ok, "status": response.status_code, "detail": response.text[:1000], "descriptor": data}
    except requests.RequestException as exc:
        return {"ok": False, "status": None, "detail": str(exc)}
