from osii.model_clients import create_chat_client, create_embedding_client


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_openai_compatible_capabilities_do_not_require_gateway_sdk(monkeypatch):
    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        if url.endswith("/chat/completions"):
            return FakeResponse({"choices": [{"message": {"content": "grounded answer"}}]})
        return FakeResponse({"data": [{"embedding": [0.1, 0.2]}]})

    monkeypatch.setenv("OSII_MODEL_BASE_URL", "https://models.example.test/v1")
    monkeypatch.setenv("OSII_MODEL_API_KEY", "test-token")
    monkeypatch.setattr("osii.model_clients.requests.post", fake_post)

    answer = create_chat_client().complete(
        model="example-chat",
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=32,
    )
    vectors = create_embedding_client().embed(model="example-embed", texts=["hello"])

    assert answer == "grounded answer"
    assert vectors == [[0.1, 0.2]]
    assert calls[0]["url"] == "https://models.example.test/v1/chat/completions"
    assert calls[1]["url"] == "https://models.example.test/v1/embeddings"
    assert calls[0]["headers"]["Authorization"] == "Bearer test-token"
