#!/usr/bin/env python3
"""Verify the portable OpenAI-compatible contract without logging secrets."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


def _environment(name: str) -> str:
    return os.getenv(name, "").strip()


def _request(base_url: str, api_key: str, path: str, payload: dict[str, Any] | None, timeout: float) -> tuple[dict[str, Any], dict[str, str]]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}", data=data, headers=headers,
        method="POST" if payload is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            decoded = json.loads(response.read().decode("utf-8"))
            return decoded, dict(response.headers.items())
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as exc:
        # Do not include the response body: commercial gateways can echo a
        # request, and this command is intended to be safe for support logs.
        if isinstance(exc, urllib.error.HTTPError):
            raise RuntimeError(f"HTTP {exc.code} calling {path}") from exc
        raise RuntimeError(f"Could not call {path}: {exc}") from exc


def _model_ids(payload: dict[str, Any]) -> list[str]:
    rows = payload.get("data")
    if not isinstance(rows, list):
        return []
    return [str(row.get("id")) for row in rows if isinstance(row, dict) and row.get("id")]


def _chat_check(base_url: str, api_key: str, model: str, timeout: float) -> dict[str, Any]:
    payload, headers = _request(
        base_url, api_key, "/chat/completions",
        {
            "model": model,
            "messages": [{"role": "user", "content": "Reply exactly with OSII_ENDPOINT_OK."}],
            "max_tokens": 12,
            "temperature": 0,
        },
        timeout,
    )
    choices = payload.get("choices")
    content = ""
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message")
        if isinstance(message, dict):
            content = str(message.get("content") or "").strip()
    if not content:
        raise RuntimeError("Chat completion returned no assistant content.")
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    return {"model": str(payload.get("model") or model), "assistant_characters": len(content), "usage_keys": sorted(usage), "request_id_present": bool(headers.get("x-request-id") or payload.get("id"))}


def _embedding_check(base_url: str, api_key: str, model: str, timeout: float) -> dict[str, Any]:
    payload, _ = _request(
        base_url, api_key, "/embeddings",
        {"model": model, "input": ["OSII embedding lifecycle check."], "encoding_format": "float"},
        timeout,
    )
    rows = payload.get("data")
    vector: Any = rows[0].get("embedding") if isinstance(rows, list) and rows and isinstance(rows[0], dict) else None
    if not isinstance(vector, list) or not vector:
        raise RuntimeError("Embedding response contained no vector.")
    return {"model": str(payload.get("model") or model), "dimensions": len(vector)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=_environment("OSII_MODEL_BASE_URL"))
    parser.add_argument("--api-key-env", default=_environment("OSII_MODEL_API_KEY_ENV") or "OSII_MODEL_API_KEY")
    parser.add_argument("--chat-model", default=_environment("OSII_CHAT_MODEL"))
    parser.add_argument("--embedding-base-url", default=_environment("OSII_EMBEDDING_BASE_URL"))
    parser.add_argument("--embedding-api-key-env", default="OSII_EMBEDDING_API_KEY")
    parser.add_argument("--embedding-model", default=_environment("OSII_EMBEDDING_MODEL"))
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    if not args.base_url or not args.chat_model:
        print("Set OSII_MODEL_BASE_URL and OSII_CHAT_MODEL before running this check.", file=sys.stderr)
        return 2
    api_key = _environment(args.api_key_env)
    if not api_key:
        print(f"Set the credential named by {args.api_key_env} before running this check.", file=sys.stderr)
        return 2

    report: dict[str, Any] = {"base_url": args.base_url.rstrip("/"), "checks": {}}
    try:
        models, _ = _request(args.base_url, api_key, "/models", None, args.timeout)
        report["checks"]["models"] = {"available": _model_ids(models), "requested_model_listed": args.chat_model in _model_ids(models)}
        report["checks"]["chat"] = _chat_check(args.base_url, api_key, args.chat_model, args.timeout)
        if args.embedding_base_url or args.embedding_model:
            if not args.embedding_base_url or not args.embedding_model:
                raise RuntimeError("Configure both OSII_EMBEDDING_BASE_URL and OSII_EMBEDDING_MODEL, or neither.")
            embedding_key = _environment(args.embedding_api_key_env) or api_key
            report["checks"]["embeddings"] = _embedding_check(args.embedding_base_url, embedding_key, args.embedding_model, args.timeout)
    except RuntimeError as exc:
        print(f"Provider check failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
