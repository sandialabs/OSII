"""Status and explicit model checks for Simple intake."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from osii.domain.processing import quick_intake

router = APIRouter(prefix="/api/intake/quick-start", tags=["quick-intake"])
Role = Literal["embedding", "language"]


class Connection(BaseModel):
    role: Role
    model: str = Field(min_length=1, max_length=200)
    protocol: Literal["openai", "ollama"] = "openai"
    endpoint: str = Field(default="", max_length=2000)
    key: str = Field(default="", max_length=4096)
    provider_id: str = Field(default="", max_length=200)
    display_name: str = Field(default="", max_length=200)


@router.get("")
def quick_start(request: Request):
    return quick_intake.status(request.app.state.osii_root.resolve())


@router.post("/check/{role}")
def check_model(request: Request, role: Role):
    try:
        return quick_intake.check(request.app.state.osii_root.resolve(), role)
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/connect")
def connect_model(request: Request, payload: Connection):
    values = payload.model_dump()
    values["endpoint"] = payload.endpoint.strip().rstrip("/")
    values["model"] = payload.model.strip()
    if not values["model"] or (not payload.provider_id and not values["endpoint"].startswith(("http://", "https://"))):
        raise HTTPException(422, "Choose a model and enter its HTTP or HTTPS endpoint.")
    try:
        return quick_intake.connect(request.app.state.osii_root.resolve(), **values)
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc
