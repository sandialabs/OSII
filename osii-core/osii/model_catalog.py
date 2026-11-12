"""Read-only model discovery shared by local Setup and hosted administration."""
import requests

from osii.model_endpoints import endpoint_from_environment


class CatalogError(ValueError):
    pass


def discover_models(base_url: str, api_key: str = "", *, protocol: str = "openai",
                    capability: str | None = None) -> list[dict]:
    """Query a catalog only; never generate text, embeddings, or rerank passages."""
    endpoint = endpoint_from_environment("chat", environment={"OSII_CHAT_BASE_URL": base_url, "OSII_CHAT_API_KEY": api_key})
    if not endpoint.base_url or protocol not in {"openai", "ollama"}:
        raise CatalogError("Enter a supported endpoint URL before finding models")
    paths = ["/api/tags"] if protocol == "ollama" else ["/models"]
    if endpoint.base_url == "https://openrouter.ai/api/v1":
        paths = (["/embeddings/models"] if capability == "embedding" else ["/models"]
                 if capability else ["/models", "/embeddings/models"])
    headers = {"Accept": "application/json"}
    if endpoint.api_key:
        headers["Authorization"] = f"Bearer {endpoint.api_key}"
    models = {}
    for path in paths:
        try:
            response = requests.get(endpoint.base_url + path, headers=headers, timeout=(3, 12), allow_redirects=False)
        except requests.RequestException:
            raise CatalogError("The endpoint could not be reached. Check its address and network access.") from None
        if response.status_code in {401, 403}:
            raise CatalogError("The endpoint rejected access. Check its API key and permissions.")
        if not response.ok or 300 <= response.status_code < 400:
            raise CatalogError("This endpoint did not publish a model list. You can enter its model name manually.")
        try:
            payload = response.json()
            rows = payload.get("data", payload.get("models"))
            if not isinstance(rows, list) or len(rows) > 5000:
                raise ValueError()
            for row in rows:
                if not isinstance(row, dict):
                    continue
                identifier = (row.get("model") or row.get("name")) if protocol == "ollama" else (row.get("id") or row.get("name"))
                if not isinstance(identifier, str) or not identifier or len(identifier) > 200:
                    continue
                modalities = (row.get("architecture") or {}).get("output_modalities", [])
                if modalities and not any(value in modalities for value in ("text", "embeddings")):
                    continue
                caps = row.get("capabilities") or []
                caps = [name for name in caps if name in {"chat", "embedding", "rerank"}] if isinstance(caps, list) else []
                if path == "/embeddings/models" or "embeddings" in modalities:
                    caps = ["embedding"]
                elif "text" in modalities:
                    caps = ["chat"]
                elif row.get("endpoints"):
                    caps = [name for name in ("chat", "embedding", "rerank")
                            if ("embed" if name == "embedding" else name) in row["endpoints"]]
                if capability and caps and capability not in caps:
                    continue
                models[identifier] = {"id": identifier, "name": str(row.get("name") or identifier)[:300], "capabilities": caps}
        except (ValueError, AttributeError, TypeError):
            raise CatalogError("The endpoint returned an unreadable model list. Check the API base address.") from None
    return sorted(models.values(), key=lambda model: (model["name"].casefold(), model["id"]))
