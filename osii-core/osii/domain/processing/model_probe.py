"""Small explicit inference checks shared by model setup and intake."""

from math import isfinite

import requests


def probe_model(base_url: str, protocol: str, token: str, model: str, capability: str) -> dict:
    ollama = protocol == "ollama"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    path = ("/api/embed" if ollama else "/embeddings") if capability == "embedding" else ("/api/chat" if ollama else "/chat/completions")
    body = {"model": model, "input": ["OSII connection test"]} if capability == "embedding" else {
        "model": model, "messages": [{"role": "user", "content": "Reply OK."}],
        **({"stream": False, "options": {"num_predict": 8}} if ollama else {"max_tokens": 8})}
    try:
        response = requests.post(base_url.rstrip("/") + path, headers=headers, json=body, timeout=(3, 20))
        response.raise_for_status()
        result = response.json()
        if capability == "embedding":
            vector = (result.get("embeddings") or [None])[0] if ollama else (result.get("data") or [{}])[0].get("embedding")
            if not (isinstance(vector, list) and vector and all(isinstance(x, (int, float)) and not isinstance(x, bool) and isfinite(x) for x in vector)):
                raise ValueError("No usable numeric embedding vector returned")
            return {"ok": True, "model": model, "capability": capability, "dimensions": len(vector)}
        message = result.get("message") if ollama else (result.get("choices") or [{}])[0].get("message")
        if not isinstance(message, dict) or not (message.get("content") or message.get("reasoning_content")):
            raise ValueError("No generated text returned")
        return {"ok": True, "model": model, "capability": capability}
    except (requests.RequestException, ValueError, TypeError, AttributeError, IndexError) as exc:
        from osii.processor_sdk.diagnostics import redact
        return {"ok": False, "model": model, "capability": capability, "detail": redact(str(exc))}
