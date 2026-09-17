from __future__ import annotations

import re
import time
import uuid
from pathlib import Path
from typing import Any

import requests
from fastapi import APIRouter, HTTPException, Request

from osii.configuration import (
    builtin_tools_config,
    configured_tools,
    load_models_config,
    load_tools_config,
    save_tools_config,
)


router = APIRouter(prefix="/api/admin/processors", tags=["processor-administration"])
VALID_KINDS = {"extractor", "synthesizer", "embedder", "enricher"}
_DESCRIPTOR_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _headers(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


def _descriptor(base_url: str, token: str | None = None) -> dict[str, Any]:
    try:
        response = requests.get(
            f"{base_url.rstrip('/')}/v1/descriptor",
            headers=_headers(token),
            timeout=8,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not read a valid Processor API descriptor: {exc}",
        ) from exc
    if not isinstance(data, dict) or data.get("kind") not in VALID_KINDS or not data.get("name"):
        raise HTTPException(status_code=422, detail="The service returned an invalid Processor API descriptor")
    return data


def _cached_descriptor(base_url: str) -> dict[str, Any]:
    now = time.monotonic()
    cached = _DESCRIPTOR_CACHE.get(base_url)
    if cached and cached[0] > now:
        return cached[1]
    try:
        response = requests.get(f"{base_url}/v1/descriptor", timeout=0.5)
        response.raise_for_status()
        descriptor = response.json()
        if not isinstance(descriptor, dict) or descriptor.get("kind") not in VALID_KINDS:
            descriptor = {}
    except (requests.RequestException, ValueError):
        descriptor = {}
    _DESCRIPTOR_CACHE[base_url] = (now + 30, descriptor)
    return descriptor


def _records(osii_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for tool_id, tool in configured_tools(osii_root).items():
        if not isinstance(tool, dict):
            continue
        runtime = tool.get("runtime") if isinstance(tool.get("runtime"), dict) else {}
        endpoint = str(runtime.get("endpoint") or "").rstrip("/")
        if not endpoint:
            continue
        descriptor = _cached_descriptor(endpoint)
        records.append({
            "id": tool_id,
            "processor_id": str(tool.get("processor_id") or tool_id),
            "display_name": str(tool.get("display_name") or tool.get("processor_id") or tool_id),
            "kind": str(tool.get("kind") or "enricher"),
            "base_url": endpoint,
            "enabled": bool(tool.get("enabled", True)),
            "runtime": runtime,
            "model_access": tool.get("model_access") or {"mode": "none"},
            "model_requirements": descriptor.get("model_requirements") or tool.get("model_requirements") or {},
            "capabilities": descriptor.get("capabilities") or tool.get("capabilities") or {},
            "aliases": tool.get("aliases") or [],
        })
    return records


def _save_tool(osii_root: Path, tool_id: str, tool: dict[str, Any] | None) -> None:
    config = load_tools_config(osii_root)
    tools = config.setdefault("tools", {})
    if tool is None:
        if tool_id in builtin_tools_config()["tools"]:
            tools[tool_id] = {**builtin_tools_config()["tools"][tool_id], "enabled": False}
        else:
            tools.pop(tool_id, None)
    else:
        tools[tool_id] = tool
    save_tools_config(config)


def _tool_id(payload: dict[str, Any], processor_id: str, existing: set[str]) -> str:
    value = str(payload.get("id") or processor_id).strip().casefold()
    value = re.sub(r"[^a-z0-9_.-]+", "-", value).strip("-.")
    value = value or f"processor-{uuid.uuid4().hex[:8]}"
    if value in existing:
        raise HTTPException(status_code=409, detail=f"processor registration '{value}' already exists")
    return value


def _model_access(
    payload: dict[str, Any], descriptor: dict[str, Any], osii_root: Path
) -> dict[str, Any]:
    requirements = descriptor.get("model_requirements") or {}
    if not isinstance(requirements, dict) or not requirements:
        return {"mode": "none"}
    supplied = payload.get("model_access")
    bindings = dict(supplied.get("bindings") or {}) if isinstance(supplied, dict) else {}
    selected = str(payload.get("model_connection") or "").strip()
    defaults = load_models_config(osii_root).get("defaults", {})
    for capability, requirement in requirements.items():
        if requirement not in {"required", "optional"}:
            continue
        if selected and capability == "chat":
            bindings[capability] = selected
        bindings.setdefault(capability, str(defaults.get(capability) or ""))
        if requirement == "required" and not bindings[capability]:
            raise HTTPException(
                status_code=422,
                detail=f"This processor requires a {capability} model connection",
            )
    return {"mode": "gateway", "bindings": {key: value for key, value in bindings.items() if value}}


def _tool_from_descriptor(
    payload: dict[str, Any], descriptor: dict[str, Any], osii_root: Path
) -> dict[str, Any]:
    base_url = str(payload.get("base_url") or "").strip().rstrip("/")
    return {
        "enabled": bool(payload.get("enabled", True)),
        "processor_id": str(descriptor["name"]),
        "display_name": str(descriptor.get("display_name") or descriptor["name"]),
        "kind": str(descriptor["kind"]),
        "runtime": {"mode": "external", "endpoint": base_url},
        "model_access": _model_access(payload, descriptor, osii_root),
    }


def _health(endpoint: dict[str, Any], token: str | None = None) -> dict[str, Any]:
    try:
        response = requests.get(f"{endpoint['base_url']}/health", headers=_headers(token), timeout=5)
        return {"ok": response.ok, "status": response.status_code, "detail": response.text[:300]}
    except requests.RequestException as exc:
        return {"ok": False, "status": None, "detail": str(exc)}


@router.get("")
async def list_processor_endpoints(request: Request):
    return {"processors": _records(request.app.state.osii_root.resolve())}


@router.post("")
async def create_processor_endpoint(request: Request, payload: dict):
    osii_root = request.app.state.osii_root.resolve()
    base_url = str(payload.get("base_url") or "").strip().rstrip("/")
    if not base_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="base_url must start with http:// or https://")
    descriptor = _descriptor(base_url, payload.get("token"))
    tool_id = _tool_id(payload, str(descriptor["name"]), set(configured_tools(osii_root)))
    tool = _tool_from_descriptor({**payload, "base_url": base_url}, descriptor, osii_root)
    _save_tool(osii_root, tool_id, tool)
    return {"processor": next(item for item in _records(osii_root) if item["id"] == tool_id)}


@router.put("/{endpoint_id}")
async def update_processor_endpoint(request: Request, endpoint_id: str, payload: dict):
    osii_root = request.app.state.osii_root.resolve()
    existing = next((item for item in _records(osii_root) if item["id"] == endpoint_id), None)
    if existing is None:
        raise HTTPException(status_code=404, detail="processor endpoint not found")
    merged = {**existing, **payload}
    descriptor = _descriptor(str(merged["base_url"]), payload.get("token"))
    _save_tool(osii_root, endpoint_id, _tool_from_descriptor(merged, descriptor, osii_root))
    return {"processor": next(item for item in _records(osii_root) if item["id"] == endpoint_id)}


@router.delete("/{endpoint_id}")
async def delete_processor_endpoint(request: Request, endpoint_id: str):
    osii_root = request.app.state.osii_root.resolve()
    if endpoint_id not in configured_tools(osii_root):
        raise HTTPException(status_code=404, detail="processor endpoint not found")
    _save_tool(osii_root, endpoint_id, None)
    return {"deleted": endpoint_id}


@router.post("/{endpoint_id}/health")
async def health_processor_endpoint(request: Request, endpoint_id: str, payload: dict | None = None):
    endpoint = next((item for item in _records(request.app.state.osii_root.resolve()) if item["id"] == endpoint_id), None)
    if endpoint is None:
        raise HTTPException(status_code=404, detail="processor endpoint not found")
    return _health(endpoint, (payload or {}).get("token"))


@router.post("/{endpoint_id}/test")
async def test_processor_endpoint(request: Request, endpoint_id: str, payload: dict | None = None):
    endpoint = next((item for item in _records(request.app.state.osii_root.resolve()) if item["id"] == endpoint_id), None)
    if endpoint is None:
        raise HTTPException(status_code=404, detail="processor endpoint not found")
    token = (payload or {}).get("token")
    descriptor = _descriptor(endpoint["base_url"], token)
    expected = endpoint["processor_id"]
    aliases = set(endpoint.get("aliases") or [])
    if descriptor.get("name") != expected and descriptor.get("name") not in aliases:
        raise HTTPException(
            status_code=422,
            detail=f"descriptor name {descriptor.get('name')!r} does not match {expected!r}",
        )
    health = _health(endpoint, token)
    return {**health, "descriptor": descriptor}
