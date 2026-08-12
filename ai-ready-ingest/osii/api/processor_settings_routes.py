from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from osii.domain.processor_settings import (
    load_processor_settings,
    save_processor_settings,
)

router = APIRouter(prefix="/api/admin/processor-settings", tags=["processor-settings"])


@router.get("")
def get_processor_settings(request: Request):
    return {"settings": load_processor_settings(request.app.state.osii_root.resolve())}


@router.put("/{processor_name}")
def put_processor_settings(request: Request, processor_name: str, payload: dict):
    config = payload.get("config")
    if not isinstance(config, dict):
        raise HTTPException(status_code=422, detail="config must be an object")
    if len(json.dumps(config)) > 100_000:
        raise HTTPException(status_code=422, detail="processor settings are too large")
    saved = save_processor_settings(
        request.app.state.osii_root.resolve(),
        processor_name,
        config,
    )
    return {"processor_name": processor_name, "config": saved}
