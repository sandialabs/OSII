from __future__ import annotations

import argparse
import os
from typing import Any

import requests


def _json(response: requests.Response, operation: str) -> dict[str, Any]:
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"{operation} returned a non-object JSON response")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate the documented OpenAI-compatible HTTP contract without printing content."
    )
    parser.parse_args()

    base_url = (
        os.getenv("OPENAI_BASE_URL", "").strip()
    ).rstrip("/")
    api_key = os.getenv("OPENAI_API_KEY", "")
    model = (
        os.getenv("OPENAI_CHAT_MODEL", "").strip()
        or os.getenv("OPENAI_SYNTHESIS_MODEL", "").strip()
        or "fixture-chat-model"
    )
    if not base_url or not api_key:
        raise SystemExit(
            "Set OPENAI_BASE_URL and OPENAI_API_KEY first."
        )
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

    print(f"models: ok ({len(model_rows)} returned)")
    print("chat: ok (choices present)")


if __name__ == "__main__":
    main()
