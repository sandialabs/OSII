import requests


class OsiiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def search(self, *, query: str, mode: str, top_k: int, scope: dict) -> dict:
        response = requests.post(
            f"{self.base_url}/api/search",
            json={
                "query": query,
                "mode": mode,
                "top_k": top_k,
                "scope": scope,
            },
            timeout=120,
        )
        response.raise_for_status()
        return response.json()

    def get_object(self, file_id: str) -> dict:
        response = requests.get(
            f"{self.base_url}/api/objects/{file_id}",
            timeout=120,
        )
        response.raise_for_status()
        return response.json()

    def get_span_context(self, file_id: str, char_start: int, char_end: int, context_chars: int = 300) -> dict:
        response = requests.get(
            f"{self.base_url}/api/text/objects/{file_id}/span/context",
            params={
                "char_start": char_start,
                "char_end": char_end,
                "context_chars": context_chars,
            },
            timeout=120,
        )
        response.raise_for_status()
        return response.json()