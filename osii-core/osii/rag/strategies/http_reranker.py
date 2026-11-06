"""Optional Cohere-compatible HTTP reranking adapter owned by Core RAG."""
import requests

from osii.model_endpoints import ModelEndpoint, endpoint_from_environment
from .contracts import RankedEvidence, RerankRequest, StrategyError


class HttpReranker:
    """POST base_url + /rerank; map provider indices to original evidence IDs."""

    def __init__(self, endpoint: ModelEndpoint, *, timeout: float = 60):
        if not endpoint.base_url or not endpoint.model:
            raise StrategyError("Reranking requires both an API base URL and an exact model ID")
        if not 0 < timeout <= 600:
            raise StrategyError("Reranker timeout must be between 0 and 600 seconds")
        self.endpoint, self.timeout = endpoint, timeout

    def __call__(self, request: RerankRequest) -> tuple[RankedEvidence, ...]:
        if not request.candidates:
            return ()
        headers = {"Content-Type": "application/json"}
        if self.endpoint.api_key:
            headers["Authorization"] = f"Bearer {self.endpoint.api_key}"
        try:
            response = requests.post(self.endpoint.base_url + "/rerank", headers=headers,
                json={"model": self.endpoint.model, "query": request.query,
                      "documents": [item.text for item in request.candidates],
                      "top_n": min(request.top_k, len(request.candidates)), "return_documents": False},
                timeout=(5, self.timeout), allow_redirects=False)
        except requests.RequestException:
            raise StrategyError("The configured reranking endpoint could not be reached") from None
        if not response.ok or response.is_redirect:
            raise StrategyError(f"Reranking endpoint returned HTTP {response.status_code}")
        try:
            payload = response.json()
            rows = payload["results"]
            if not isinstance(rows, list) or len(rows) > min(request.top_k, len(request.candidates)):
                raise ValueError()
            scores, seen = [], set()
            for row in rows:
                index = row["index"]
                if type(index) is not int or not 0 <= index < len(request.candidates) or index in seen:
                    raise ValueError()
                seen.add(index)
                scores.append(RankedEvidence(request.candidates[index].id, row["relevance_score"]))
            return tuple(scores)
        except (KeyError, TypeError, ValueError):
            raise StrategyError("Reranking endpoint returned invalid indices or scores") from None


def create_reranker(endpoint: ModelEndpoint | None = None) -> HttpReranker | None:
    """No configuration means disabled; partial configuration is an error."""
    endpoint = endpoint if endpoint is not None else endpoint_from_environment("rerank")
    if not endpoint.base_url and not endpoint.model:
        return None
    return HttpReranker(endpoint)
