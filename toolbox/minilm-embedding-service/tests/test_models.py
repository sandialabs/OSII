from app.config import get_settings
from app.models import OpenAIEmbeddingItem, OpenAIEmbeddingRequest, OpenAIEmbeddingResponse, OpenAIEmbeddingUsage


def test_default_model_is_minilm(monkeypatch) -> None:
    monkeypatch.delenv("MODEL_NAME", raising=False)

    assert get_settings().model_name == "sentence-transformers/all-MiniLM-L6-v2"


def test_openai_contract_models_without_loading_a_model() -> None:
    request = OpenAIEmbeddingRequest(input=["alpha", "beta"], model="example")
    response = OpenAIEmbeddingResponse(
        data=[OpenAIEmbeddingItem(index=0, embedding=[0.0, 1.0])],
        model=request.model or "example",
        usage=OpenAIEmbeddingUsage(prompt_tokens=0, total_tokens=0),
    )

    assert request.input == ["alpha", "beta"]
    assert response.data[0].embedding == [0.0, 1.0]
