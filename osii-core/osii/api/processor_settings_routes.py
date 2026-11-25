from __future__ import annotations

import json
import os
import tomli_w
from jsonschema import validate, ValidationError

from fastapi import APIRouter, HTTPException, Request
from osii.domain.processor_settings import (
    load_processor_settings,
    save_processor_settings,
)
from osii.configuration import load_tools_config, save_tools_config, processors_path
from osii.domain.env_credentials import local_config_writable, resolve_env_value, write_env_value
from osii.processor_modules import active_processors

router = APIRouter(prefix="/api/admin/processor-settings", tags=["processor-settings"])


@router.get("")
def get_processor_settings(request: Request):
    return {"settings": load_processor_settings(request.app.state.osii_root.resolve())}


@router.get("/startup")
def get_startup_settings():
    saved = load_tools_config().get('processor_startup', {})
    return {'path': str(processors_path()), 'processors': [
        {'id': p.id, 'processor_id': p.processor_id, 'display_name': p.display_name,
         'schema': p.startup_schema, 'config': {
             name: value for name, value in saved.get(p.id, {}).items()
             if name in p.startup_schema.get('properties', {})
         },
         'credential': {'present': bool(resolve_env_value(p.credential_env)[0]),
                        'writable': local_config_writable()} if p.credential_env else None,
         'environment_overrides': [name for name in p.startup_schema.get('properties', {}) if name in os.environ]}
        for p in active_processors() if p.startup_schema.get('properties') or p.credential_env
    ]}


@router.put("/startup/{service_id}/credential")
def put_startup_credential(service_id: str, payload: dict):
    processor = next((p for p in active_processors() if p.id == service_id and p.credential_env), None)
    if processor is None:
        raise HTTPException(404, "This module has no configurable credential")
    key = payload.get("api_key")
    if not isinstance(key, str) or not key.strip() or len(key) > 8192:
        raise HTTPException(422, "Enter a valid API key")
    try:
        write_env_value(processor.credential_env, key.strip())
    except (PermissionError, ValueError) as exc:
        raise HTTPException(403, str(exc)) from exc
    return {"credential_present": True}


@router.put("/startup/{service_id}")
def put_startup_settings(service_id: str, payload: dict):
    processor = next((p for p in active_processors() if p.id == service_id and p.startup_schema), None)
    if processor is None:
        raise HTTPException(status_code=404, detail='No configurable startup settings for this service')
    config = payload.get('config')
    if len(json.dumps(config)) > 100_000:
        raise HTTPException(status_code=422, detail='startup settings are too large')
    try:
        validate(config, processor.startup_schema)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc
    configuration = load_tools_config()
    # Preserve values for other modules and unrelated configuration sections.
    configuration.setdefault('processor_startup', {})[service_id] = config
    try:
        save_tools_config(configuration)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {'id': service_id, 'config': config, 'restart_required': True}


@router.put("/{processor_name}")
def put_processor_settings(request: Request, processor_name: str, payload: dict):
    config = payload.get("config")
    if not isinstance(config, dict):
        raise HTTPException(status_code=422, detail="config must be an object")
    if len(json.dumps(config)) > 100_000:
        raise HTTPException(status_code=422, detail="processor settings are too large")
    try:
        tomli_w.dumps({"settings": config})
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"settings must use TOML-compatible values: {exc}") from exc
    try:
        saved = save_processor_settings(
            request.app.state.osii_root.resolve(),
            processor_name,
            config,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"processor_name": processor_name, "config": saved}
