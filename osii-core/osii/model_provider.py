"""Bounded provider adapter. It has no knowledge of persistence or accounts."""
from __future__ import annotations

import requests


class ProviderError(RuntimeError):
    pass


class ModelProvider:
    def __init__(self, url: str, key: str):
        self.url, self.key = url.rstrip("/"), key

    def request(self, method: str, path: str, payload: dict | None = None) -> dict:
        try:
            response = requests.request(method, self.url + path,
                headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
                json=payload, timeout=(5, 90))
        except requests.RequestException:
            raise ProviderError("The configured model endpoint could not be reached") from None
        if not response.ok:
            reasons = {401: "The provider rejected its API key", 402: "The provider reports insufficient credit",
                403: "The provider denied access to this model", 404: "The model or endpoint was not found",
                429: "The provider rate limit was reached"}
            raise ProviderError(reasons.get(response.status_code, f"Model endpoint returned HTTP {response.status_code}"))
        try:
            data = response.json()
        except ValueError:
            raise ProviderError("The endpoint returned non-JSON content. Check the API base URL, not the website URL.") from None
        if not isinstance(data, dict):
            raise ProviderError("The endpoint returned an unsupported JSON response")
        return data

    def catalog(self) -> list[dict]:
        data = self.request("GET", "/models")
        results = {}
        for model in data.get("data", []):
            if not isinstance(model, dict) or not model.get("id"):
                continue
            modalities = (model.get("architecture") or {}).get("output_modalities", [])
            results[str(model["id"])] = {"id": str(model["id"]), "name": str(model.get("name") or model["id"]),
                "capabilities": ["embedding"] if "embeddings" in modalities else ["chat"] if "text" in modalities else []}
        # OpenRouter publishes embeddings separately. Generic compatible endpoints
        # need not implement this; unknown capabilities remain selectable manually.
        if self.url == "https://openrouter.ai/api/v1":
            for model in self.request("GET", "/embeddings/models").get("data", []):
                if model.get("id"):
                    results[str(model["id"])] = {"id": str(model["id"]), "name": str(model.get("name") or model["id"]), "capabilities": ["embedding"]}
        return sorted(results.values(), key=lambda m: (m["name"].casefold(), m["id"]))

    def chat(self, model: str, messages: list[dict], max_tokens: int = 900) -> tuple[str, dict]:
        data = self.request("POST", "/chat/completions", {"model": model, "messages": messages, "max_tokens": max_tokens})
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise ProviderError("The model returned no usable answer") from None
        if not isinstance(content, str) or not content.strip():
            raise ProviderError("The model returned an empty answer")
        return content.strip(), {k: data.get("usage", {}).get(k) for k in ("prompt_tokens", "completion_tokens", "cost")}

    def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        data = self.request("POST", "/embeddings", {"model": model, "input": texts})
        try:
            rows = sorted(data["data"], key=lambda row: row["index"])
            vectors = [[float(v) for v in row["embedding"]] for row in rows]
            if len(vectors) != len(texts) or not vectors or not vectors[0] or any(len(v) != len(vectors[0]) for v in vectors):
                raise ValueError()
            import math
            if not all(math.isfinite(v) for vector in vectors for v in vector):
                raise ValueError()
            return vectors
        except (KeyError, ValueError, TypeError):
            raise ProviderError("The model returned invalid embedding vectors") from None
