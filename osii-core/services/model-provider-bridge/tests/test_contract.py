from fastapi.testclient import TestClient
import pytest
import requests

from app.main import CLIENTS, app
from osii.configuration import save_models_config
from osii.model_gateway_tokens import issue_model_gateway_token
from tests.fake_openai_server import app as fake_openai_app


def test_named_connection_does_not_inherit_another_providers_key(monkeypatch, tmp_path):
    monkeypatch.setattr("app.main._configured_provider", lambda *a: {
        "base_url": "https://embedding.test/v1", "credential_env": "OSII_EMBEDDING_API_KEY"})
    monkeypatch.setenv("OSII_ENV_FILE", str(tmp_path / "empty.env"))
    monkeypatch.setenv("OPENAI_API_KEY", "shared-must-not-leak")
    monkeypatch.setenv("OSII_MODEL_API_KEY", "other-must-not-leak")
    monkeypatch.delenv("OSII_EMBEDDING_API_KEY", raising=False)
    monkeypatch.delenv("OSII_EMBEDDING_API_KEY_FILE", raising=False)
    assert "Authorization" not in CLIENTS["openai"].headers(capability="embedding")
    monkeypatch.setenv("OSII_EMBEDDING_API_KEY", "embedding-key")
    assert CLIENTS["openai"].headers(capability="embedding")["Authorization"] == "Bearer embedding-key"


@pytest.fixture(autouse=True)
def isolated_model_configuration(monkeypatch, tmp_path):
    """Contract tests must not read the developer's saved model connections."""
    monkeypatch.setenv("OSII_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OSII_ENV_FILE", str(tmp_path / "config" / "secrets.env"))


def test_provider_client_preserves_ollama_context_error(monkeypatch):
    response = requests.Response()
    response.status_code = 400
    response._content = b'{"error":"the input length exceeds the context length"}'

    monkeypatch.setattr(requests, "request", lambda *args, **kwargs: response)
    with pytest.raises(ValueError, match="exceeds the context length"):
        CLIENTS["ollama"].request("POST", "/api/embed", payload={"input": ["long"]})


def test_ollama_embedding_and_synthesis_contract(monkeypatch):
    monkeypatch.setenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
    monkeypatch.setenv("OLLAMA_SYNTHESIS_MODEL", "gemma3:4b")

    def fake_request(method, path, **kwargs):
        if path == "/api/embed":
            return {"model": "nomic-embed-text", "embeddings": [[0.0, 1.0]]}
        if path == "/api/chat":
            return {"message": {"content": "# Grounded preview"}}
        if path == "/api/tags":
            return {"models": [{"name": "nomic-embed-text"}]}
        raise AssertionError(path)

    monkeypatch.setattr(CLIENTS["ollama"], "request", fake_request)
    client = TestClient(app)
    descriptor = client.get("/ollama/embedder/v1/descriptor").json()
    assert descriptor["name"] == "ollama.embedder"
    embedded = client.post("/ollama/embedder/v1/embed", json={"request_id": "r1", "inputs": [{"id": "a", "text": "hello"}]})
    assert embedded.status_code == 200
    assert embedded.json()["vectors"] == [{"id": "a", "vector": [0.0, 1.0], "dimensions": 2}]
    synthesized = client.post("/ollama/synthesizer/v1/synthesize", json={"config":{"extract_metadata":False},"request_id": "r2", "scope": {"scope_type": "object", "scope_id": "a", "documents": [{"file_id": "a", "filename": "a.txt", "text": "hello"}]}})
    assert synthesized.status_code == 200
    assert synthesized.json()["metadata"]["provider"] == "ollama"


def test_synthesis_passes_wiki_guidance_and_output_limit_to_ollama(monkeypatch, tmp_path):
    monkeypatch.setenv("OSII_ROOT", str(tmp_path))
    seen = {}

    def fake_request(method, path, **kwargs):
        assert path == "/api/chat"
        seen.update(kwargs["payload"])
        return {"message": {"content": "# Demonstration Wiki\n\nGrounded fact [doc-1]."}}

    monkeypatch.setattr(CLIENTS["ollama"], "request", fake_request)
    response = TestClient(app).post(
        "/ollama/synthesizer/v1/synthesize",
        json={
            "request_id": "wiki-1",
            "scope": {
                "scope_type": "object",
                "scope_id": "doc-1",
                "documents": [{"file_id": "doc-1", "filename": "report.txt", "text": "Grounded fact."}],
            },
            "expert_context": "Focus on experimental results.",
            "config": {
                "instructions": "Create a grounded wiki.",
                "max_tokens": 1800,
                "extract_metadata": False,
            },
        },
    )

    assert response.status_code == 200
    assert "Create a grounded wiki." in seen["messages"][0]["content"]
    assert "Focus on experimental results." in seen["messages"][0]["content"]
    assert "SOURCE doc-1" in seen["messages"][0]["content"]
    assert seen["options"]["num_predict"] == 1800


def test_ollama_embedding_has_small_us_model_default(monkeypatch, tmp_path):
    monkeypatch.setenv("OSII_ROOT", str(tmp_path))
    monkeypatch.delenv("OLLAMA_EMBEDDING_MODEL", raising=False)
    seen = {}

    def fake_request(method, path, **kwargs):
        seen.update(kwargs["payload"])
        return {"model": "all-minilm", "embeddings": [[1.0, 0.0]]}

    monkeypatch.setattr(CLIENTS["ollama"], "request", fake_request)
    monkeypatch.setattr("app.main._ollama_model_digest", lambda _: None)
    response = TestClient(app).post("/ollama/embedder/v1/embed", json={"request_id": "r", "inputs": [{"id": "a", "text": "hello"}]})
    assert response.status_code == 200
    assert seen["model"] == "all-minilm"


def test_openai_chat_and_synthesis_use_openai_compatible_route(monkeypatch, tmp_path):
    monkeypatch.setenv("OSII_ROOT", str(tmp_path))
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "openai-chat-v1")
    monkeypatch.setenv("OPENAI_SYNTHESIS_MODEL", "openai-chat-v1")
    calls = []

    def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs["payload"]))
        if path == "/embeddings":
            return {
                "model": kwargs["payload"]["model"],
                "data": [{"index": 0, "embedding": [0.25, 0.75]}],
            }
        return {
            "model": kwargs["payload"]["model"],
            "choices": [
                {"message": {"content": "# OpenAI-compatible-grounded output"}, "finish_reason": "stop"}
            ],
        }

    monkeypatch.setattr(CLIENTS["openai"], "request", fake_request)
    client = TestClient(app)
    descriptor = client.get("/openai/synthesizer/v1/descriptor").json()
    synthesis = client.post(
        "/openai/synthesizer/v1/synthesize",
        json={
            "request_id": "s1",
            "config": {"extract_metadata": False},
            "scope": {
                "scope_type": "object",
                "scope_id": "doc-1",
                "documents": [
                    {"file_id": "doc-1", "filename": "report.txt", "text": "Grounded fact."}
                ],
            },
        },
    )
    chat = client.post(
        "/openai/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "Hello"}]},
    )
    embedded = client.post(
        "/openai/embedder/v1/embed",
        json={
            "request_id": "e1",
            "inputs": [{"id": "doc-1", "text": "Grounded fact."}],
            "config": {"model": "openai-embed-v1"},
        },
    )

    assert descriptor["name"] == "openai.synthesizer"
    assert synthesis.status_code == 200
    assert synthesis.json()["metadata"]["provider"] == "openai"
    assert chat.status_code == 200
    assert embedded.status_code == 200
    assert embedded.json()["vectors"][0]["dimensions"] == 2
    assert embedded.json()["metadata"]["endpoint_type"] == "openai-compatible"
    assert chat.json()["provider"] == "openai"
    assert [path for _, path, _ in calls].count("/chat/completions") == 2
    assert [path for _, path, _ in calls].count("/embeddings") == 1


def test_openai_http_uses_standard_environment_variables(monkeypatch, tmp_path):
    monkeypatch.setenv("OSII_ROOT", str(tmp_path))
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openai.example.test/api/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "alias-key")
    seen = {}

    class Response:
        text = ""
        status_code = 200

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"data": []}

    def fake_request(method, url, **kwargs):
        assert method == "GET"
        seen["url"] = url
        seen.update(kwargs)
        return Response()

    monkeypatch.setattr(requests, "request", fake_request)
    payload = CLIENTS["openai"].request("GET", "/models")

    assert payload == {"data": []}
    assert seen["url"] == "https://openai.example.test/api/v1/models"
    assert seen["headers"]["Authorization"] == "Bearer alias-key"


def test_openai_http_reads_api_key_from_container_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("OSII_ROOT", str(tmp_path))
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openai.example.test/api/v1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    secret = tmp_path / "openai_api_key"
    secret.write_text("secret-file-key\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY_FILE", str(secret))
    seen = {}

    class Response:
        text = ""
        status_code = 200

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"data": []}

    def fake_request(method, url, **kwargs):
        seen.update(kwargs)
        return Response()

    monkeypatch.setattr(requests, "request", fake_request)
    CLIENTS["openai"].request("GET", "/models")

    assert seen["headers"]["Authorization"] == "Bearer secret-file-key"


def test_openai_embedding_retries_without_optional_encoding_format(monkeypatch, tmp_path):
    monkeypatch.setenv("OSII_ROOT", str(tmp_path))
    calls = []

    def fake_request(method, path, **kwargs):
        calls.append(kwargs["payload"])
        if "encoding_format" in kwargs["payload"]:
            raise ValueError("optional field is not supported")
        return {"model": "embed-v1", "data": [{"embedding": [1.0, 0.0]}]}

    monkeypatch.setattr(CLIENTS["openai"], "request", fake_request)
    response = TestClient(app).post(
        "/openai/embedder/v1/embed",
        json={
            "request_id": "retry",
            "inputs": [{"id": "doc", "text": "hello"}],
            "config": {"model": "embed-v1"},
        },
    )

    assert response.status_code == 200
    assert len(calls) == 2
    assert "encoding_format" not in calls[1]


def test_fake_openai_server_enforces_contract():
    client = TestClient(fake_openai_app)
    assert client.get("/api/v1/models").status_code == 401
    headers = {"Authorization": "Bearer local-emulator-key"}
    models = client.get("/api/v1/models", headers=headers)
    chat = client.post(
        "/api/v1/chat/completions",
        headers=headers,
        json={
            "model": "fixture-chat-model",
            "messages": [{"role": "user", "content": "Hello"}],
        },
    )
    embeddings = client.post(
        "/api/v1/embeddings",
        headers=headers,
        json={"model": "fixture-embedding-model", "input": ["hello"]},
    )
    assert embeddings.status_code == 200
    assert len(embeddings.json()["data"][0]["embedding"]) == 3

    assert models.status_code == 200
    assert chat.json()["choices"][0]["message"]["content"]


def test_model_gateway_forwards_alias_to_configured_openai_model(monkeypatch, tmp_path):
    monkeypatch.setenv("OSII_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OSII_MODEL_GATEWAY_SECRET", "test-gateway-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "provider-secret")
    save_models_config({
        "version": 1,
        "models": {
            "top": {
                "type": "openai-compatible",
                "base_url": "https://models.example.test/v1",
                "api_key_env": "OPENAI_API_KEY",
                "model": "vendor/high-quality-instruct",
                "capabilities": ["chat", "synthesis"],
            }
        },
        "defaults": {"chat": "top", "synthesis": "top"},
    })
    seen = {}

    class Response:
        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {
                "id": "chatcmpl-upstream",
                "object": "chat.completion",
                "model": "vendor/high-quality-instruct",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "Grounded."}, "finish_reason": "stop"}],
            }

    def fake_request(method, url, **kwargs):
        seen.update({"method": method, "url": url, **kwargs})
        return Response()

    monkeypatch.setattr(requests, "request", fake_request)
    token = issue_model_gateway_token(
        tool_id="readable-llm-wiki",
        job_id="job-1",
        bindings={"chat": "top"},
        max_requests=3,
    )
    response = TestClient(app).post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {token}"},
        json={"model": "top", "messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 200
    assert seen["url"] == "https://models.example.test/v1/chat/completions"
    assert seen["json"]["model"] == "vendor/high-quality-instruct"
    assert seen["headers"]["Authorization"] == "Bearer provider-secret"
    assert response.json()["osii"] == {"connection": "top", "provider_type": "openai-compatible"}


def test_model_gateway_token_cannot_select_another_connection(monkeypatch, tmp_path):
    monkeypatch.setenv("OSII_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OSII_MODEL_GATEWAY_SECRET", "test-gateway-secret")
    save_models_config({
        "version": 1,
        "models": {
            "mid": {"type": "ollama-local", "base_url": "http://127.0.0.1:11434", "model": "model-mid", "capabilities": ["chat"]},
            "top": {"type": "ollama-local", "base_url": "http://127.0.0.1:11434", "model": "model-top", "capabilities": ["chat"]},
        },
        "defaults": {"chat": "mid"},
    })
    token = issue_model_gateway_token(tool_id="concept-wiki", job_id="job-2", bindings={"chat": "mid"})

    response = TestClient(app).post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {token}"},
        json={"model": "top", "messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 403


def test_model_gateway_token_stops_working_when_job_revokes_it(monkeypatch):
    monkeypatch.setenv("OSII_MODEL_GATEWAY_SECRET", "test-gateway-secret")
    token = issue_model_gateway_token(
        tool_id="readable-llm-wiki",
        job_id="completed-job",
        bindings={"chat": "top"},
    )
    headers = {"Authorization": f"Bearer {token}"}
    client = TestClient(app)

    assert client.get("/v1/models", headers=headers).status_code == 200
    assert client.post("/v1/tokens/revoke", headers=headers).status_code == 200
    rejected = client.get("/v1/models", headers=headers)

    assert rejected.status_code == 401
    assert "no longer active" in rejected.json()["detail"]


def test_long_synthesis_windows_cover_all_text_and_resume_successful_calls():
    from osii.processor_sdk import SynthesisRequest
    from osii.processors.text import chat_synthesizer_descriptor
    from osii.processors.synthesis import synthesize_bounded, synthesis_call_estimate
    text = 'START_MARKER ' + 'x' * 205550 + ' END_MARKER'
    request = SynthesisRequest(request_id='bounded', config={'extract_metadata':False}, scope={'scope_type':'object', 'scope_id':'doc',
        'documents':[{'file_id':'doc','filename':'OPAQUE.pdf','text':text}]})
    saved={}; calls=[]; failed=[False]
    def checkpoint(key, value=None):
        if value is not None: saved[key]=value
        return saved.get(key)
    def complete(messages):
        calls.append(messages[0]['content'])
        if len(calls)==2 and not failed[0]:
            failed[0]=True
            raise ValueError('synthetic transient provider failure')
        return '# Gardening and Landscape Design\n\nGrounded summary [doc].', {}
    with pytest.raises(ValueError, match='synthetic transient'):
        synthesize_bounded(request,chat_synthesizer_descriptor(),'test-model',complete,checkpoint=checkpoint)
    result=synthesize_bounded(request,chat_synthesizer_descriptor(),'test-model',complete,checkpoint=checkpoint)
    assert result.metadata['input_windows']==3
    assert result.metadata['model_calls']==synthesis_call_estimate(len(text),extract_metadata=False)==4
    assert result.metadata['document_title']=='Gardening and Landscape Design'
    assert result.metadata['title_method']=='model_generated'
    assert sum('START_MARKER' in prompt for prompt in calls)==1
    assert any('END_MARKER' in prompt for prompt in calls)
    assert len(calls)==5  # one failed request; first successful window was reused
    assert all(len(prompt)<101000 for prompt in calls)
    request.config={'max_input_windows':1}
    with pytest.raises(ValueError,match='window budget'):
        synthesize_bounded(request,chat_synthesizer_descriptor(),'test-model',lambda _: pytest.fail('Budget checked before model call'))


def test_synthesis_titles_are_optional_metadata_and_multi_source_has_no_document_title():
    from osii.processor_sdk import SynthesisRequest
    from osii.processors.text import chat_synthesizer_descriptor, model_synthesis_response, LocalExtractivePreviewSynthesizer
    request=SynthesisRequest(request_id='titles',scope={'scope_type':'object', 'scope_id':'doc',
        'documents':[{'file_id':'doc','filename':'OPAQUE.pdf','text':'Practical Gardening Handbook\nDetailed source text.'}]})
    response=model_synthesis_response(request,chat_synthesizer_descriptor(),'# Summary\nGrounded output','test')
    assert response.metadata['document_title']=='Practical Gardening Handbook'
    assert response.metadata['title_method']=='source_first_line'
    assert LocalExtractivePreviewSynthesizer().synthesize(request).metadata['title_method']=='source_first_line'
    request.scope.documents.append(request.scope.documents[0])
    assert 'document_title' not in model_synthesis_response(request,chat_synthesizer_descriptor(),'# Combined Sources','test').metadata
