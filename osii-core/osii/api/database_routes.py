"""Composition-supplied authorization around the reusable read-only explorer."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from osii.domain.storage.database_query import (
    DatabaseExplorer,
    QueryBusy,
    QueryRejected,
    QueryUnavailable,
)
from pydantic import BaseModel, ConfigDict, Field


class DatabaseQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sql: str = Field(min_length=1, max_length=16_000)
    limit: int = Field(default=100, ge=1, le=200, strict=True)


def create_database_router(
    explorer_for_request: Callable[[Request], DatabaseExplorer | None],
    *,
    authorize: Callable[..., Any],
    audit: Callable[[Any, str, str], None] | None = None,
) -> APIRouter:
    """Authorization is mandatory at composition time, never inferred in Core."""
    router = APIRouter(prefix="/api/admin/database", tags=["database-inspection"])
    permission = Depends(authorize)

    @router.get("/schema")
    def schema(request: Request, principal=permission):
        explorer = explorer_for_request(request)
        if explorer is None:
            return {
                "available": False,
                "backend": "sidecar",
                "tables": [],
                "detail": "Database explorer requires the explicitly selected PostgreSQL backend. Sidecars are unchanged.",
            }
        try:
            return explorer.schema()
        except QueryUnavailable as exc:
            raise HTTPException(503, str(exc)) from None

    @router.post("/query")
    def query(request: Request, payload: DatabaseQuery, principal=permission):
        explorer = explorer_for_request(request)
        if explorer is None:
            raise HTTPException(
                409, "Select PostgreSQL explicitly before using database inspection."
            )
        outcome = "rejected"
        try:
            result = explorer.query(payload.sql, limit=payload.limit)
            outcome = "completed"
            return result
        except QueryRejected as exc:
            raise HTTPException(422, str(exc)) from None
        except QueryBusy as exc:
            raise HTTPException(429, str(exc)) from None
        except QueryUnavailable as exc:
            raise HTTPException(503, str(exc)) from None
        finally:
            if audit is not None:
                # Never persist SQL text, results or database credentials.
                try:
                    audit(
                        principal,
                        outcome,
                        hashlib.sha256(payload.sql.encode()).hexdigest(),
                    )
                except Exception:  # noqa: BLE001 -- Fail closed without leaking audit backend errors.
                    raise HTTPException(
                        503, "Database inspection audit is unavailable. Retry later."
                    ) from None

    return router
