from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import requests


DEFAULT_MODEL = "meta-llama/Llama-3.1-8B-Instruct"


def _json(response: requests.Response, operation: str) -> dict[str, Any]:
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"{operation} returned a non-object JSON response")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate the documented Shirty HTTP contract without printing content."
    )
    parser.add_argument("document", type=Path, help="Harmless PDF, image, or text fixture.")
    args = parser.parse_args()

    base_url = (
        os.getenv("SHIRTY_BASE_URL", "").strip()
        or os.getenv("OPENAI_BASE_URL", "").strip()
    ).rstrip("/")
    api_key = os.getenv("SHIRTY_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
    model = (
        os.getenv("SHIRTY_CHAT_MODEL", "").strip()
        or os.getenv("SHIRTY_SYNTHESIS_MODEL", "").strip()
        or DEFAULT_MODEL
    )
    if not base_url or not api_key:
        raise SystemExit(
            "Set SHIRTY_BASE_URL/SHIRTY_API_KEY or their OPENAI_* aliases first."
        )
    if not args.document.is_file():
        raise SystemExit(f"Fixture does not exist: {args.document}")

    headers = {"Authorization": f"Bearer {api_key}"}
    models = _json(
        requests.get(f"{base_url}/models", headers=headers, timeout=(3, 15)),
        "model discovery",
    )
    model_rows = models.get("data") or models.get("models")
    if not isinstance(model_rows, list):
        raise RuntimeError("model discovery did not return data/models list")

    chat = _json(
        requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with the single word OK."}],
                "max_tokens": 8,
            },
            timeout=(3, 60),
        ),
        "chat completion",
    )
    choices = chat.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("chat completion did not return choices")

    with args.document.open("rb") as handle:
        extraction = _json(
            requests.post(
                f"{base_url}/extract/textract/create",
                headers=headers,
                files={"file": (args.document.name, handle)},
                timeout=(3, 180),
            ),
            "Textract",
        )
    text = extraction.get("text")
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("Textract did not return non-empty text")

    print(f"models: ok ({len(model_rows)} returned)")
    print("chat: ok (choices present)")
    print(f"textract: ok ({len(text)} characters; content not printed)")


if __name__ == "__main__":
    main()
