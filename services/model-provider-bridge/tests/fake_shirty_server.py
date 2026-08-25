from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
import requests


DEFAULT_MODEL = "meta-llama/Llama-3.1-8B-Instruct"
app = FastAPI(
    title="OSII Fake Shirty Contract Server",
    description="Test-only server for the documented Shirty HTTP surface.",
)


def _authorize(authorization: str | None) -> None:
    expected = os.getenv("SHIRTY_EMULATOR_API_KEY", "local-emulator-key")
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="invalid emulator credential")


@app.get("/api/v1/models")
def models(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _authorize(authorization)
    model = os.getenv("SHIRTY_EMULATOR_MODEL", DEFAULT_MODEL)
    return {"object": "list", "data": [{"id": model, "object": "model"}]}


@app.post("/api/v1/chat/completions")
def chat(
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _authorize(authorization)
    upstream = os.getenv("SHIRTY_EMULATOR_UPSTREAM_BASE_URL", "").rstrip("/")
    if upstream:
        key_env = os.getenv("SHIRTY_EMULATOR_UPSTREAM_API_KEY_ENV", "TOGETHER_API_KEY")
        upstream_payload = dict(payload)
        upstream_payload["model"] = os.getenv(
            "SHIRTY_EMULATOR_UPSTREAM_MODEL", str(payload.get("model") or DEFAULT_MODEL)
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
                    "content": "Deterministic Shirty contract-emulator response.",
                },
                "finish_reason": "stop",
            }
        ],
    }


@app.post("/api/v1/extract/textract/create")
async def extract(
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _authorize(authorization)
    content = await file.read()
    tesseract_url = os.getenv("SHIRTY_EMULATOR_TESSERACT_URL", "").rstrip("/")
    if tesseract_url:
        response = requests.post(
            f"{tesseract_url}/ocr/document",
            files={
                "file": (
                    file.filename or "document",
                    content,
                    file.content_type or "application/octet-stream",
                )
            },
            data={"language": os.getenv("SHIRTY_EMULATOR_OCR_LANGUAGE", "en")},
            timeout=(3, 180),
        )
        response.raise_for_status()
        payload = response.json()
        pages = []
        for page in payload.get("pages", []):
            page_text = "\n".join(
                str(item.get("text") or "").strip()
                for item in page.get("results", [])
                if isinstance(item, dict) and item.get("text")
            )
            pages.append({"page": page.get("page"), "text": page_text})
        return {
            "text": "\n\n".join(page["text"] for page in pages if page["text"]),
            "pages": pages,
        }

    if (file.content_type or "").startswith("text/"):
        text = content.decode("utf-8")
    else:
        text = "Deterministic extraction fixture; configure SHIRTY_EMULATOR_TESSERACT_URL for OCR."
    return {"text": text}
