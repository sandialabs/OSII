"""Bounded provider adapter. It has no knowledge of persistence or accounts."""
from __future__ import annotations

import requests
import time
from osii.model_endpoints import ModelEndpoint


class ProviderError(RuntimeError):
    pass


class ModelProvider:
    def __init__(self, url: str, key: str, *, embedding_endpoint: ModelEndpoint | None = None):
        self.url, self.key = url.rstrip("/"), key
        self.embedding_provider = (ModelProvider(embedding_endpoint.base_url, embedding_endpoint.api_key)
            if embedding_endpoint is not None and (embedding_endpoint.base_url, embedding_endpoint.api_key) != (self.url, key) else None)

    def request(self, method: str, path: str, payload: dict | None = None) -> dict:
        # Retry only embedding reads: retrying chat after a lost response can
        # duplicate a generation and its charge. Each request has three attempts.
        attempts = 3 if path == "/embeddings" else 1
        for attempt in range(attempts):
            try:
                headers = {"Content-Type": "application/json"}
                if self.key:
                    headers["Authorization"] = f"Bearer {self.key}"
                response = requests.request(method, self.url + path,
                    headers=headers, json=payload, timeout=(5, 90), allow_redirects=False)
            except requests.RequestException:
                if attempt + 1 == attempts:
                    raise ProviderError(f"The configured model endpoint could not be reached after {attempts} attempt(s)") from None
                time.sleep(2 ** attempt)
                continue
            if response.ok or response.status_code not in (408, 429, 500, 502, 503, 504) or attempt + 1 == attempts:
                break
            try:
                delay = min(30, max(2 ** attempt, float(response.headers.get("Retry-After", 0))))
            except (ValueError, TypeError):
                delay = 2 ** attempt
            time.sleep(delay)
        if not response.ok or 300 <= getattr(response, "status_code", 200) < 400:
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
        chat = self._catalog()
        if self.embedding_provider is None:
            return chat
        models = {(row["id"], "chat"): {**row, "capabilities": ["chat"]} for row in chat if "embedding" not in row["capabilities"]}
        for row in self.embedding_provider._catalog():
            if "chat" not in row["capabilities"]:
                models[(row["id"], "embedding")] = {**row, "capabilities": ["embedding"]}
        return sorted(models.values(), key=lambda row: (row["name"].casefold(), row["id"]))

    def _catalog(self) -> list[dict]:
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
        if self.embedding_provider is not None:
            return self.embedding_provider.embed(model, texts)
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
