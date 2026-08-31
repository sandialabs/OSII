from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, Header, HTTPException
import requests


DEFAULT_MODEL = "meta-llama/Llama-3.1-8B-Instruct"
app = FastAPI(
    title="OSII Fake OpenAI-compatible Contract Server",
    description="Test-only server for the documented OpenAI-compatible HTTP surface.",
)


def _authorize(authorization: str | None) -> None:
    expected = os.getenv("OPENAI_EMULATOR_API_KEY", "local-emulator-key")
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="invalid emulator credential")


@app.get("/api/v1/models")
def models(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _authorize(authorization)
    model = os.getenv("OPENAI_EMULATOR_MODEL", DEFAULT_MODEL)
    return {"object": "list", "data": [{"id": model, "object": "model"}]}


@app.post("/api/v1/chat/completions")
def chat(
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _authorize(authorization)
    upstream = os.getenv("OPENAI_EMULATOR_UPSTREAM_BASE_URL", "").rstrip("/")
    if upstream:
        key_env = os.getenv("OPENAI_EMULATOR_UPSTREAM_API_KEY_ENV", "TOGETHER_API_KEY")
        upstream_payload = dict(payload)
        upstream_payload["model"] = os.getenv(
            "OPENAI_EMULATOR_UPSTREAM_MODEL", str(payload.get("model") or DEFAULT_MODEL)
        )
        response = requests.post(
            f"{upstream}/chat/completions",
            headers={"Authorization": f"Bearer {os.getenv(key_env, '')}"},
            json=upstream_payload,
            timeout=(3, 180),
        )
        response.raise_for_status()
        return response.json()

    model = str(payload.get("model") or DEFAULT_MODEL)
    return {
        "id": "chatcmpl-osii-fixture",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Deterministic OpenAI-compatible contract-emulator response.",
                },
                "finish_reason": "stop",
            }
        ],
    }


@app.post("/api/v1/embeddings")
def embeddings(
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _authorize(authorization)
    values = payload.get("input") or []
    if isinstance(values, str):
        values = [values]
    return {
        "object": "list",
        "model": str(payload.get("model") or "fixture-embedding-model"),
        "data": [
            {"object": "embedding", "index": index, "embedding": [float(len(str(value))), 1.0, 0.0]}
            for index, value in enumerate(values)
        ],
    }
