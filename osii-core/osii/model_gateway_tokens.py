"""Small signed, short-lived grants for the internal Model Gateway."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Any


def _secret() -> bytes:
    return os.getenv("OSII_MODEL_GATEWAY_SECRET", "osii-local-development").encode("utf-8")


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_model_gateway_token(
    *,
    tool_id: str,
    job_id: str,
    bindings: dict[str, str],
    ttl_seconds: int = 900,
    max_requests: int = 64,
) -> str:
    now = int(time.time())
    claims = {
        "v": 1,
        "jti": uuid.uuid4().hex,
        "tool": tool_id,
        "job": job_id,
        "bindings": bindings,
        "iat": now,
        "exp": now + ttl_seconds,
        "max_requests": max_requests,
    }
    payload = _encode(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = _encode(hmac.new(_secret(), payload.encode("ascii"), hashlib.sha256).digest())
    return f"{payload}.{signature}"


def verify_model_gateway_token(token: str) -> dict[str, Any]:
    try:
        payload, signature = token.split(".", 1)
        expected = _encode(hmac.new(_secret(), payload.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid signature")
        claims = json.loads(_decode(payload))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid Model Gateway token") from exc
    if not isinstance(claims, dict) or int(claims.get("exp", 0)) <= int(time.time()):
        raise ValueError("Model Gateway token has expired")
    if not isinstance(claims.get("bindings"), dict):
        raise ValueError("Model Gateway token has no model bindings")
    return claims
