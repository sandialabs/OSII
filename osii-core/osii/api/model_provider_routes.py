from __future__ import annotations

import json
import os
from pathlib import Path
import re
import threading
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
import requests

from osii.domain.model_provider_config import (
    DEFAULT_OLLAMA_CHAT_MODEL,
    DEFAULT_OLLAMA_EMBEDDING_MODEL,
)
from osii.domain.env_credentials import (
    local_config_writable,
    resolve_env_value,
    write_env_value,
)
from osii.configuration import load_models_config, save_models_config


router = APIRouter(prefix="/api/admin/model-providers", tags=["model-provider-administration"])
VALID_TYPES = {"ollama", "openai"}
RECOMMENDED_OLLAMA_MODELS = [
    {
        "model": DEFAULT_OLLAMA_EMBEDDING_MODEL,
        "capability": "embedding",
        "display_name": "MiniLM embeddings",
        "publisher": "Microsoft-origin MiniLM",
        "size_label": "about 46 MB",
        "description": "Small 384-dimensional semantic embedding baseline.",
    },
    {
        "model": DEFAULT_OLLAMA_CHAT_MODEL,
        "capability": "chat",
        "display_name": "Llama 3.2 1B",
        "publisher": "Meta",
        "size_label": "about 1.3 GB",
        "description": "Small instruction model for chat and grounded synthesis.",
    },
]
PULL_JOBS: dict[str, dict[str, Any]] = {}
PULL_JOBS_LOCK = threading.Lock()


def _load(osii_root) -> list[dict[str, Any]]:
    """Present connection-oriented models.toml through the legacy provider UI shape."""
    config = load_models_config(osii_root)
    defaults = config.get("defaults") or {}
    records = []
    for alias, connection in (config.get("models") or {}).items():
        if not isinstance(connection, dict):
            continue
        capabilities = set(connection.get("capabilities") or [])
        model = str(connection.get("model") or "")
        records.append({
            "id": str(alias),
            "type": "ollama" if connection.get("type") == "ollama-local" else "openai",
            "base_url": str(connection.get("base_url") or "").rstrip("/"),
            "enabled": bool(connection.get("enabled", True)),
            "priority": int(connection.get("priority", 100)),
            "embedding_model": model if "embedding" in capabilities else "",
            "synthesis_model": model if "synthesis" in capabilities else "",
            "chat_model": model if "chat" in capabilities else "",
            "credential_env": str(connection.get("api_key_env") or ""),
            "default_chat": str(defaults.get("chat") or "") == str(alias),
            "default_embedding": str(defaults.get("embedding") or "") == str(alias),
        })
    by_id = {str(item["id"]): item for item in records}
    merged: list[dict[str, Any]] = []
    consumed: set[str] = set()
    for record in records:
        identifier = str(record["id"])
        if identifier in consumed or identifier.endswith("-embedding"):
            continue
        sibling_id = f"{identifier}-embedding"
        sibling = by_id.get(sibling_id)
        if sibling and sibling.get("type") == record.get("type") and sibling.get("base_url") == record.get("base_url"):
            record = {
                **record,
                "embedding_model": sibling.get("embedding_model", ""),
                "default_embedding": bool(sibling.get("default_embedding")),
            }
            consumed.add(sibling_id)
        merged.append(record)
    merged.extend(
        record for record in records
        if str(record["id"]).endswith("-embedding") and str(record["id"]) not in consumed
    )
    return merged


def _with_runtime_defaults(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = list(records)
    if not any(item.get("type") == "ollama" for item in result):
        result.append({"id": "ollama-local", "type": "ollama", "base_url": os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"), "enabled": True, "priority": 100, "embedding_model": os.getenv("OLLAMA_EMBEDDING_MODEL", "").strip() or DEFAULT_OLLAMA_EMBEDDING_MODEL, "synthesis_model": os.getenv("OLLAMA_SYNTHESIS_MODEL", "").strip() or DEFAULT_OLLAMA_CHAT_MODEL, "chat_model": os.getenv("OLLAMA_CHAT_MODEL", "").strip() or DEFAULT_OLLAMA_CHAT_MODEL, "credential_env": "", "default_chat": True, "default_embedding": True, "implicit": True})
    openai_configured = bool(os.getenv("OPENAI_BASE_URL", "").strip())
    if openai_configured and not any(item.get("type") == "openai" for item in result):
        result.append({
            "id": "openai-compatible",
            "type": "openai",
            "base_url": os.getenv("OPENAI_BASE_URL", "").strip().rstrip("/"),
            "enabled": True,
            "priority": 10,
            "embedding_model": os.getenv("OPENAI_EMBEDDING_MODEL", "").strip(),
            "synthesis_model": os.getenv("OPENAI_SYNTHESIS_MODEL", "").strip(),
            "chat_model": os.getenv("OPENAI_CHAT_MODEL", "").strip(),
            "credential_env": "OPENAI_API_KEY",
            "default_chat": True,
            "default_embedding": bool(os.getenv("OPENAI_EMBEDDING_MODEL", "").strip()),
            "implicit": True,
        })
    return result


def _save(osii_root, records: list[dict[str, Any]]) -> None:
    current = load_models_config(osii_root)
    old_defaults = dict(current.get("defaults") or {})
    models: dict[str, dict[str, Any]] = {}
    language_aliases: list[str] = []
    embedding_aliases: list[str] = []
    requested_chat_default = ""
    requested_embedding_default = ""
    for record in records:
        identifier = str(record["id"])
        provider_type = "ollama-local" if record.get("type") == "ollama" else "openai-compatible"
        common = {
            "type": provider_type,
            "base_url": str(record.get("base_url") or "").rstrip("/"),
            "enabled": bool(record.get("enabled", True)),
            "priority": int(record.get("priority", 100)),
        }
        credential_env = str(record.get("credential_env") or "").strip()
        if credential_env:
            common["api_key_env"] = credential_env
        language = str(record.get("chat_model") or record.get("synthesis_model") or "").strip()
        embedding = str(record.get("embedding_model") or "").strip()
        if language:
            alias = identifier
            models[alias] = {**common, "model": language, "capabilities": ["chat", "synthesis"]}
            language_aliases.append(alias)
            if record.get("default_chat"):
                requested_chat_default = alias
        if embedding:
            alias = identifier if not language or embedding == language else f"{identifier}-embedding"
            capabilities = ["embedding"] if embedding != language else ["chat", "synthesis", "embedding"]
            models[alias] = {**common, "model": embedding, "capabilities": capabilities}
            embedding_aliases.append(alias)
            if record.get("default_embedding"):
                requested_embedding_default = alias
        if not language and not embedding:
            models[identifier] = {**common, "model": "", "capabilities": []}
    chat_default = requested_chat_default or (
        str(old_defaults.get("chat") or "")
        if str(old_defaults.get("chat") or "") in language_aliases
        else (language_aliases[0] if language_aliases else "")
    )
    embedding_default = requested_embedding_default or (
        str(old_defaults.get("embedding") or "")
        if str(old_defaults.get("embedding") or "") in embedding_aliases
        else (embedding_aliases[0] if embedding_aliases else "")
    )
    current["defaults"] = {
        **({"chat": chat_default, "synthesis": chat_default} if chat_default else {}),
        **({"embedding": embedding_default} if embedding_default else {}),
    }
    current["models"] = models
    save_models_config(current)


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
        "default_chat": bool(payload.get("default_chat", False)),
        "default_embedding": bool(payload.get("default_embedding", False)),
    }


def _public(record: dict[str, Any]) -> dict[str, Any]:
    credential_env = record.get("credential_env") or ("" if record.get("type") == "ollama" else "OPENAI_API_KEY")
    credential, source = resolve_env_value(str(credential_env))
    return {
        **record,
        "credential_required": record.get("type") != "ollama",
        "credential_present": bool(credential),
        "credential_source": source,
        "credential_writable": local_config_writable() and source != "environment",
        "credential_value": None,
    }


def _saved_credential_name(record: dict[str, Any]) -> str:
    if record.get("type") == "openai" and record.get("id") == "openai-compatible":
        return "OPENAI_API_KEY"
    configured = str(record.get("credential_env") or "").strip()
    if configured and configured != "OSII_MODEL_API_KEY":
        return configured
    suffix = re.sub(r"[^A-Z0-9]+", "_", str(record["id"]).upper()).strip("_")
    return f"OSII_PROVIDER_{suffix}_API_KEY"


def _provider(osii_root: Path, provider_id: str) -> dict[str, Any] | None:
    records = _with_runtime_defaults(_load(osii_root))
    record = next((item for item in records if item.get("id") == provider_id), None)
    if record is None:
        return None
    embedding = next(
        (item for item in records if item.get("id") == f"{provider_id}-embedding"),
        None,
    )
    if embedding and not record.get("embedding_model"):
        record = {**record, "embedding_model": embedding.get("embedding_model", "")}
    return record


def _allowed_ollama_models() -> set[str]:
    configured = {
        item.strip()
        for item in os.getenv(
            "OSII_OLLAMA_ALLOWED_MODELS",
            f"{DEFAULT_OLLAMA_EMBEDDING_MODEL},{DEFAULT_OLLAMA_CHAT_MODEL}",
        ).split(",")
        if item.strip()
    }
    return configured


def _model_details(payload: dict[str, Any]) -> list[dict[str, Any]]:
    models = payload.get("models") or payload.get("data") or []
    result = []
    for item in models:
        if not isinstance(item, dict):
            continue
        details = item.get("details") if isinstance(item.get("details"), dict) else {}
        name = item.get("model") or item.get("name") or item.get("id")
        if not name:
            continue
        result.append({
            "name": str(name),
            "size": item.get("size"),
            "digest": item.get("digest"),
            "modified_at": item.get("modified_at"),
            "family": details.get("family"),
            "parameter_size": details.get("parameter_size"),
            "quantization_level": details.get("quantization_level"),
        })
    return result


def _probe_openai_embedding(
    record: dict[str, Any], headers: dict[str, str]
) -> dict[str, Any]:
    model = str(record.get("embedding_model") or "").strip()
    if not model:
        return {
            "configured": False,
            "ok": False,
            "model": "",
            "detail": "No embedding model is selected.",
        }
    payloads = [
        {"model": model, "input": ["OSII embedding connection test"], "encoding_format": "float"},
        {"model": model, "input": ["OSII embedding connection test"]},
    ]
    last_error = "The endpoint did not return an embedding vector."
    for payload in payloads:
        try:
            response = requests.post(
                f"{record['base_url']}/embeddings",
                headers=headers,
                json=payload,
                timeout=(3, 15),
            )
            response.raise_for_status()
            rows = response.json().get("data") or []
            vector = rows[0].get("embedding") if rows and isinstance(rows[0], dict) else None
            if isinstance(vector, list) and vector:
                return {
                    "configured": True,
                    "ok": True,
                    "model": model,
                    "dimensions": len(vector),
                    "detail": f"Validated a {len(vector)}-dimensional embedding vector.",
                }
            last_error = "The endpoint responded without a usable embedding vector."
        except (requests.RequestException, ValueError, AttributeError) as exc:
            last_error = str(exc)
    return {
        "configured": True,
        "ok": False,
        "model": model,
        "detail": f"Embedding test failed: {last_error}",
    }


def _probe_ollama_embedding(record: dict[str, Any]) -> dict[str, Any]:
    model = str(record.get("embedding_model") or "").strip()
    if not model:
        return {
            "configured": False,
            "ok": False,
            "model": "",
            "detail": "No embedding model is selected.",
        }
    try:
        response = requests.post(
            f"{record['base_url']}/api/embed",
            json={"model": model, "input": ["OSII embedding connection test"]},
            timeout=(3, 15),
        )
        response.raise_for_status()
        rows = response.json().get("embeddings") or []
        vector = rows[0] if rows and isinstance(rows[0], list) else None
        if vector:
            return {
                "configured": True,
                "ok": True,
                "model": model,
                "dimensions": len(vector),
                "detail": f"Validated a {len(vector)}-dimensional embedding vector.",
            }
        detail = "Ollama responded without a usable embedding vector."
    except (requests.RequestException, ValueError, AttributeError) as exc:
        detail = str(exc)
    return {
        "configured": True,
        "ok": False,
        "model": model,
        "detail": f"Embedding test failed: {detail}",
    }


def _run_ollama_pull(job_id: str, base_url: str, model: str) -> None:
    try:
        with requests.post(
            f"{base_url}/api/pull",
            json={"model": model, "stream": True},
            stream=True,
            timeout=(5, 300),
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                update = json.loads(line)
                if not isinstance(update, dict):
                    raise ValueError("Ollama returned an invalid model-download update")
                if update.get("error"):
                    raise ValueError(str(update["error"]))
                with PULL_JOBS_LOCK:
                    job = PULL_JOBS[job_id]
                    job["status_text"] = str(update.get("status") or "Downloading")
                    job["completed"] = int(update.get("completed") or 0)
                    job["total"] = int(update.get("total") or 0)
        with PULL_JOBS_LOCK:
            PULL_JOBS[job_id].update({"status": "complete", "status_text": "Installed"})
    except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
        with PULL_JOBS_LOCK:
            PULL_JOBS[job_id].update({"status": "error", "status_text": "Download failed", "detail": str(exc)})


@router.get("")
def list_providers(request: Request):
    records = sorted(_with_runtime_defaults(_load(request.app.state.osii_root.resolve())), key=lambda item: (int(item.get("priority", 100)), item.get("id", "")))
    return {"providers": [_public(item) for item in records], "ollama_recommendations": RECOMMENDED_OLLAMA_MODELS}


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
    removed = next((item for item in records if item.get("id") == provider_id), None)
    retained = [item for item in records if item.get("id") != provider_id]
    if len(retained) == len(records):
        raise HTTPException(status_code=404, detail="model provider not found")
    if removed is not None:
        credential_name = _saved_credential_name(removed)
        _, source = resolve_env_value(credential_name)
        if source == "repo_env" and local_config_writable():
            write_env_value(credential_name, None)
    _save(root, retained)
    return {"deleted": provider_id}


@router.post("/{provider_id}/health")
def provider_health(request: Request, provider_id: str):
    record = _provider(request.app.state.osii_root.resolve(), provider_id)
    if not record:
        raise HTTPException(status_code=404, detail="model provider not found")
    path = "/api/tags" if record["type"] == "ollama" else "/models"
    env_name = record.get("credential_env") or ("" if record["type"] == "ollama" else "OPENAI_API_KEY")
    token, _ = resolve_env_value(str(env_name))
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        response = requests.get(f"{record['base_url']}{path}", headers=headers, timeout=(3, 8))
        response.raise_for_status()
        payload = response.json()
        model_details = _model_details(payload)
        names = [item["name"] for item in model_details]
        selected = {record.get("embedding_model"), record.get("synthesis_model"), record.get("chat_model")} - {"", None}
        missing = sorted(
            model for model in selected
            if not any(name == model or name == f"{model}:latest" or model == f"{name}:latest" for name in names)
        ) if record["type"] == "ollama" else []
        capabilities = {}
        if record["type"] == "openai":
            capabilities["embedding"] = _probe_openai_embedding(record, headers)
        else:
            capabilities["embedding"] = _probe_ollama_embedding(record)
        return {"ok": True, "models": names, "model_details": model_details, "missing_models": missing, "pull_commands": [f"ollama pull {name}" for name in missing], "recommendations": RECOMMENDED_OLLAMA_MODELS if record["type"] == "ollama" else [], "capabilities": capabilities}
    except (requests.RequestException, ValueError) as exc:
        return {"ok": False, "models": [], "model_details": [], "missing_models": [], "pull_commands": [], "recommendations": RECOMMENDED_OLLAMA_MODELS if record["type"] == "ollama" else [], "detail": str(exc)}


@router.put("/{provider_id}/credential")
def save_provider_credential(request: Request, provider_id: str, payload: dict):
    root = request.app.state.osii_root.resolve()
    records = _load(root)
    record = next((item for item in records if item.get("id") == provider_id), None)
    if record is None:
        raise HTTPException(status_code=404, detail="model provider not found")
    if record.get("type") == "ollama":
        raise HTTPException(status_code=422, detail="Ollama does not use an API key")
    current_name = str(record.get("credential_env") or "OPENAI_API_KEY")
    _, current_source = resolve_env_value(current_name)
    if current_source == "environment":
        raise HTTPException(status_code=409, detail="This credential is managed by the process environment")
    name = _saved_credential_name(record)
    value = str(payload.get("api_key") or "")
    if not value:
        raise HTTPException(status_code=422, detail="api_key is required")
    try:
        write_env_value(name, value)
    except (PermissionError, ValueError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    for index, current in enumerate(records):
        if current.get("id") == provider_id:
            records[index] = {**current, "credential_env": name}
            break
    _save(root, records)
    return {"provider_id": provider_id, "credential_present": True, "credential_source": "repo_env"}


@router.delete("/{provider_id}/credential")
def delete_provider_credential(request: Request, provider_id: str):
    record = _provider(request.app.state.osii_root.resolve(), provider_id)
    if record is None:
        raise HTTPException(status_code=404, detail="model provider not found")
    current_name = str(record.get("credential_env") or "OPENAI_API_KEY")
    _, current_source = resolve_env_value(current_name)
    if current_source == "environment":
        raise HTTPException(status_code=409, detail="This credential is managed by the process environment")
    name = _saved_credential_name(record)
    try:
        write_env_value(name, None)
    except (PermissionError, ValueError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"provider_id": provider_id, "credential_present": False, "credential_source": None}


@router.post("/{provider_id}/models/pull")
def pull_model(request: Request, provider_id: str, payload: dict):
    record = _provider(request.app.state.osii_root.resolve(), provider_id)
    if not record:
        raise HTTPException(status_code=404, detail="model provider not found")
    if record.get("type") != "ollama":
        raise HTTPException(status_code=422, detail="model downloads are supported only for Ollama")
    model = str(payload.get("model") or "").strip()
    if model not in _allowed_ollama_models():
        raise HTTPException(status_code=403, detail="model is not in OSII_OLLAMA_ALLOWED_MODELS")
    with PULL_JOBS_LOCK:
        existing = next((job for job in PULL_JOBS.values() if job["provider_id"] == provider_id and job["model"] == model and job["status"] in {"queued", "running"}), None)
        if existing:
            return existing
        job_id = uuid.uuid4().hex
        job = {"job_id": job_id, "provider_id": provider_id, "model": model, "status": "queued", "status_text": "Starting download", "completed": 0, "total": 0, "detail": None}
        PULL_JOBS[job_id] = job
    thread = threading.Thread(target=_run_ollama_pull, args=(job_id, str(record["base_url"]), model), daemon=True)
    with PULL_JOBS_LOCK:
        PULL_JOBS[job_id]["status"] = "running"
    thread.start()
    return job


@router.get("/{provider_id}/models/pull/{job_id}")
def pull_status(request: Request, provider_id: str, job_id: str):
    del request
    with PULL_JOBS_LOCK:
        job = PULL_JOBS.get(job_id)
        if not job or job.get("provider_id") != provider_id:
            raise HTTPException(status_code=404, detail="model download job not found")
        return dict(job)
