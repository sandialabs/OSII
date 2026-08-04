from fastapi.testclient import TestClient

from app.main import app


def test_chat_falls_back_and_labels_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("OSII_ROOT", str(tmp_path))
    monkeypatch.setenv("CHAT_PROVIDER", "openai")
    monkeypatch.setenv("CHAT_PROVIDER_CHAIN", "openai,extractive")
    monkeypatch.setattr("app.main.retrieve_with_fallback", lambda **_: ("lexical", {"results": [{"file_id": "a", "filename": "a.txt", "snippet": "grounded evidence"}]}))

    def completion(**kwargs):
        if kwargs["provider"] == "openai":
            raise RuntimeError("provider down")
        return "extractive answer"

    monkeypatch.setattr("app.main.run_chat_completion", completion)
    response = TestClient(app).post("/api/chat", json={"query": "What?", "scope": {"scope_type": "root"}})
    assert response.status_code == 200
    assert response.json()["provider"] == "extractive"
    assert response.json()["fallback_used"] is True
    assert response.json()["retrieval_mode"] == "lexical"
