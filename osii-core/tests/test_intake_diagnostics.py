import errno
import io
import json
import urllib.error
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from osii.processor_sdk import Extractor, ProcessorDescriptor, ProcessorKind, create_processor_app, ProcessorClient, ProcessorClientError
from osii.processor_sdk.diagnostics import failure, retry_file_access


def test_processor_exception_reports_own_environment_without_key(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "private-process-key")
    secrets = tmp_path / "secrets.env"
    secrets.write_text('OPENAI_API_KEY="private-saved-key"\n')
    monkeypatch.setenv("OSII_ENV_FILE", str(secrets))
    class Broken(Extractor):
        descriptor = ProcessorDescriptor(name="test.broken", version="1", display_name="Broken", description="Failure fixture", kind=ProcessorKind.EXTRACTOR)
        def extract(self, request):
            raise ModuleNotFoundError("No module named fastapi private-process-key private-saved-key")
    client = TestClient(create_processor_app(Broken()), raise_server_exceptions=False)
    response = client.post("/v1/extract", json={"request_id": "test", "document": {"filename": "test.pdf"}})
    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["processor"] == "test.broken"
    assert detail["runtime"] == "Processor service"
    assert "ModuleNotFoundError" in detail["traceback"]
    assert detail["python"]["executable"]
    assert "fastapi" in detail["python"]["packages"]
    assert "private-process-key" not in response.text
    assert "private-saved-key" not in response.text


def test_only_transient_file_access_retries(monkeypatch):
    delays = []
    monkeypatch.setattr("osii.processor_sdk.diagnostics.time.sleep", delays.append)
    attempts = []
    def slow():
        attempts.append(1)
        if len(attempts) < 3:
            raise OSError(errno.ETIMEDOUT, "share is slow")
        return b"complete"
    assert retry_file_access(slow) == b"complete"
    assert delays == [1, 3]
    delays.clear()
    with pytest.raises(PermissionError):
        retry_file_access(lambda: (_ for _ in ()).throw(PermissionError("denied")))
    assert delays == []
    with pytest.raises(TimeoutError):
        retry_file_access(lambda: (_ for _ in ()).throw(TimeoutError("offline")))
    assert delays == [1, 3]


def test_processor_client_keeps_long_remote_error_and_endpoint(monkeypatch):
    body = json.dumps({"detail": "full traceback " + "x" * 5000}).encode()
    def rejected(*a, **kw):
        raise urllib.error.HTTPError("http://processor.test/v1/extract", 500, "failed", {}, io.BytesIO(body))
    monkeypatch.setattr("urllib.request.urlopen", rejected)
    with pytest.raises(ProcessorClientError) as error:
        ProcessorClient("http://processor.test")._post("/v1/extract", "{}")
    assert "http://processor.test/v1/extract" in str(error.value)
    assert body.decode() in str(error.value)


def test_preflight_executes_sample_and_reports_failure(client, monkeypatch):
    from osii.processor_sdk import ProcessorClient
    monkeypatch.setattr("osii.processors.remote.resolve_remote_processor", lambda *a: {
        "base_url": "http://processor.test", "name": "test.extractor", "capabilities": {"file_extensions": [".pdf"]}})
    monkeypatch.setattr("osii.domain.processor_settings.merged_processor_settings", lambda *a: {})
    calls = []
    def extract(self, request):
        calls.append(request)
        return SimpleNamespace(segments=["test text"])
    monkeypatch.setattr(ProcessorClient, "extract", extract)
    payload = {"processors": [{"name": "test.extractor", "kind": "extractor"}]}
    result = client.post("/api/intake/preflight", json=payload)
    assert result.status_code == 200
    assert result.json()["results"][0]["ok"] is True
    assert calls[0].document.filename == "osii-test.pdf"
    assert calls[0].document.content_base64
    monkeypatch.setattr(ProcessorClient, "extract", lambda *a: (_ for _ in ()).throw(ModuleNotFoundError("fastapi")))
    result = client.post("/api/intake/preflight", json=payload).json()["results"][0]
    assert result["ok"] is False
    assert result["diagnostics"]["endpoint"] == "http://processor.test"
    assert "ModuleNotFoundError" in result["diagnostics"]["traceback"]
