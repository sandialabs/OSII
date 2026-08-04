from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from fastapi import APIRouter, HTTPException, Request
import requests


router = APIRouter(prefix="/api/admin/model-providers", tags=["model-provider-administration"])
VALID_TYPES = {"ollama", "openai", "shirty"}


def _path(osii_root: Path) -> Path:
    path = osii_root / "state" / "model_providers.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load(osii_root: Path) -> list[dict[str, Any]]:
    try:
        value = json.loads(_path(osii_root).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def _with_runtime_defaults(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = list(records)
    known = {item.get("id") for item in result}
    if "ollama-local" not in known:
        result.append({"id": "ollama-local", "type": "ollama", "base_url": os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"), "enabled": False, "priority": 100, "embedding_model": os.getenv("OLLAMA_EMBEDDING_MODEL", ""), "synthesis_model": os.getenv("OLLAMA_SYNTHESIS_MODEL", ""), "chat_model": os.getenv("OLLAMA_CHAT_MODEL", ""), "credential_env": ""})
    return result


def _save(osii_root: Path, records: list[dict[str, Any]]) -> None:
    target = _path(osii_root)
    descriptor, temporary = tempfile.mkstemp(prefix="model-providers-", suffix=".json", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(records, handle, indent=2)
            handle.write("\n")
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _validate(payload: dict[str, Any], provider_id: str | None = None) -> dict[str, Any]:
    identifier = str(provider_id or payload.get("id") or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", identifier):
        raise HTTPException(status_code=422, detail="id must use lowercase letters, numbers, dots, underscores, or hyphens")
    provider_type = str(payload.get("type") or "").strip().lower()
    if provider_type not in VALID_TYPES:
        raise HTTPException(status_code=422, detail=f"type must be one of {sorted(VALID_TYPES)}")
    base_url = str(payload.get("base_url") or "").strip().rstrip("/")
    if not base_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="base_url must start with http:// or https://")
    credential_env = str(payload.get("credential_env") or "").strip()
    if credential_env and not re.fullmatch(r"[A-Z_][A-Z0-9_]*", credential_env):
        raise HTTPException(status_code=422, detail="credential_env must be an environment-variable name, not a credential")
    return {
        "id": identifier,
        "type": provider_type,
        "base_url": base_url,
        "enabled": bool(payload.get("enabled", False)),
        "priority": int(payload.get("priority", 100)),
        "embedding_model": str(payload.get("embedding_model") or "").strip(),
        "synthesis_model": str(payload.get("synthesis_model") or "").strip(),
        "chat_model": str(payload.get("chat_model") or "").strip(),
        "credential_env": credential_env,
    }


def _public(record: dict[str, Any]) -> dict[str, Any]:
    credential_env = record.get("credential_env") or ("SHIRTY_API_KEY" if record.get("type") == "shirty" else "OSII_MODEL_API_KEY")
    return {**record, "credential_present": bool(os.getenv(str(credential_env))), "credential_value": None}


@router.get("")
def list_providers(request: Request):
    records = sorted(_with_runtime_defaults(_load(request.app.state.osii_root.resolve())), key=lambda item: (int(item.get("priority", 100)), item.get("id", "")))
    return {"providers": [_public(item) for item in records]}


@router.post("")
def create_provider(request: Request, payload: dict):
    root = request.app.state.osii_root.resolve()
    records = _load(root)
    record = _validate(payload)
    if any(item.get("id") == record["id"] for item in records):
        raise HTTPException(status_code=409, detail="provider id already exists")
    records.append(record)
    _save(root, records)
    return {"provider": _public(record)}


@router.put("/{provider_id}")
def update_provider(request: Request, provider_id: str, payload: dict):
    root = request.app.state.osii_root.resolve()
    records = _load(root)
    for index, current in enumerate(records):
        if current.get("id") == provider_id:
            record = _validate({**current, **payload}, provider_id)
            records[index] = record
            _save(root, records)
            return {"provider": _public(record)}
    record = _validate(payload, provider_id)
    records.append(record)
    _save(root, records)
    return {"provider": _public(record)}


@router.delete("/{provider_id}")
def delete_provider(request: Request, provider_id: str):
    root = request.app.state.osii_root.resolve()
    records = _load(root)
    retained = [item for item in records if item.get("id") != provider_id]
    if len(retained) == len(records):
        raise HTTPException(status_code=404, detail="model provider not found")
    _save(root, retained)
    return {"deleted": provider_id}


@router.post("/{provider_id}/health")
def provider_health(request: Request, provider_id: str):
    record = next((item for item in _with_runtime_defaults(_load(request.app.state.osii_root.resolve())) if item.get("id") == provider_id), None)
    if not record:
        raise HTTPException(status_code=404, detail="model provider not found")
    path = "/api/tags" if record["type"] == "ollama" else "/models"
    env_name = record.get("credential_env") or ("SHIRTY_API_KEY" if record["type"] == "shirty" else "OSII_MODEL_API_KEY")
    token = os.getenv(env_name, "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        response = requests.get(f"{record['base_url']}{path}", headers=headers, timeout=(3, 8))
        response.raise_for_status()
        payload = response.json()
        models = payload.get("models") or payload.get("data") or []
        names = [item.get("model") or item.get("name") or item.get("id") for item in models if isinstance(item, dict)]
        selected = {record.get("embedding_model"), record.get("synthesis_model"), record.get("chat_model")} - {"", None}
        missing = sorted(selected - set(names)) if record["type"] == "ollama" else []
        return {"ok": True, "models": names, "missing_models": missing, "pull_commands": [f"ollama pull {name}" for name in missing]}
    except (requests.RequestException, ValueError) as exc:
        return {"ok": False, "models": [], "missing_models": [], "pull_commands": [], "detail": str(exc)}
