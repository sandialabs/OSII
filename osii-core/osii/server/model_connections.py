"""Server composition of deployment defaults and administrator-owned connections."""
from osii.model_endpoints import ModelEndpoint, endpoint_from_environment
from osii.model_provider import ModelProvider, ProviderError
from osii.rag.strategies.http_reranker import create_reranker


class ModelConnections:
    def __init__(self, store, settings):
        self.store, self.settings = store, settings

    def endpoints(self) -> dict[str, ModelEndpoint]:
        endpoints = self.settings.endpoints()
        for kind, record in self.store.setting("model_endpoints", {}).items():
            if kind in endpoints:
                endpoints[kind] = ModelEndpoint(record["base_url"], record.get("api_key", ""), record.get("model", ""))
        return endpoints

    def public(self) -> dict:
        saved = self.store.setting("model_endpoints", {})
        choices = self.store.configuration()
        result = {}
        for kind, endpoint in self.endpoints().items():
            model = choices.get(kind + "_model", "") if kind != "rerank" else endpoint.model
            name = choices.get(kind + "_model_name", model) if kind != "rerank" else saved.get(kind, {}).get("model_name", model)
            result[kind] = {**endpoint.public(), "model": model, "model_name": name,
                            "managed_by": "administrator" if kind in saved else "deployment"}
        return result

    def preview(self, kind: str, payload: dict) -> ModelEndpoint:
        current = self.endpoints()[kind]
        url = payload["base_url"].strip().rstrip("/")
        # Reusing a key at a changed address requires the administrator to enter it.
        key = current.api_key if url == current.base_url else ""
        if payload.get("clear_api_key"):
            key = ""
        elif payload.get("api_key") is not None:
            key = payload["api_key"]
        prefix = f"OSII_{kind.upper()}"
        return endpoint_from_environment(kind, environment={prefix + "_BASE_URL": url,
            prefix + "_API_KEY": key, prefix + "_MODEL": payload.get("model") or ""})

    def save(self, kind: str, payload: dict) -> dict:
        endpoint = self.preview(kind, payload)
        if kind == "rerank":
            create_reranker(endpoint)  # Validate the pair; no model invocation.
        self.store.save_model_connection(kind, {"base_url": endpoint.base_url, "api_key": endpoint.api_key,
            "model": endpoint.model, "model_name": payload.get("model_name", "")},
            model=payload.get("model"), model_name=payload.get("model_name", ""))
        return self.public()[kind]

    def reset(self, kind: str) -> None:
        self.store.save_model_connection(kind, None, model="")

    def provider(self) -> ModelProvider:
        endpoints = self.endpoints()
        chat = endpoints["chat"]
        return ModelProvider(chat.base_url, chat.api_key, embedding_endpoint=endpoints["embedding"])


class ConfiguredModelProvider:
    """Resolve current server connections at invocation, including in the worker."""
    def __init__(self, connections: ModelConnections):
        self.connections = connections

    def chat(self, model, messages, max_tokens=900):
        if not self.connections.endpoints()["chat"].base_url:
            raise ProviderError("Chat endpoint is disabled")
        return self.connections.provider().chat(model, messages, max_tokens)

    def embed(self, model, texts):
        if not self.connections.endpoints()["embedding"].base_url:
            raise ProviderError("Embedding endpoint is disabled; keyword search remains available")
        return self.connections.provider().embed(model, texts)

    def catalog(self):
        models, self.catalog_errors = {}, {}
        for kind in ("chat", "embedding"):
            endpoint = self.connections.endpoints()[kind]
            if not endpoint.base_url:
                continue
            try:
                for row in ModelProvider(endpoint.base_url, endpoint.api_key).catalog():
                    if row["capabilities"] and kind not in row["capabilities"]:
                        continue
                    models[(row["id"], kind)] = {**row, "capabilities": [kind]}
            except ProviderError as exc:
                self.catalog_errors[kind] = str(exc)
        return sorted(models.values(), key=lambda row: (row["name"].casefold(), row["id"]))
