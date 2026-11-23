import base64
import io
import tomllib
import wave
from pathlib import Path
from types import SimpleNamespace

import faster_whisper
import pytest
from fastapi.testclient import TestClient
from osii_whisper import main


def wav(num_samples=1600):
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        stream.writeframes(b"\x00\x10" * num_samples)
    return output.getvalue()


def request(raw=None, filename="recording.wav", **config):
    return {
        "request_id": "test",
        "document": {
            "filename": filename,
            "content_base64": base64.b64encode(wav() if raw is None else raw).decode(),
        },
        "config": config,
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    path = tmp_path / "approved-whisper-base"
    path.mkdir()
    for name in main.MODEL_FILES:
        (path / name).touch()
    monkeypatch.setenv("OSII_WHISPER_MODEL_DIR", str(path))
    return TestClient(main.create_processor_app(main.WhisperExtractor()))


def test_descriptor_matches_manifest_and_service_is_opt_in():
    manifest = tomllib.loads(
        (Path(__file__).parents[1] / "processor-module.toml").read_text()
    )["processors"][0]
    with TestClient(main.app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/openapi.json").status_code == 200
        descriptor = client.get("/v1/descriptor").json()
    assert descriptor["name"] == manifest["processor_id"]
    assert (
        descriptor["capabilities"]["file_extensions"]
        == manifest["capabilities"]["file_extensions"]
    )
    assert descriptor["config_schema"] == manifest["config_schema"]
    assert manifest["enabled_by_default"] is False


def test_audio_decode_transcription_and_model_reuse(client, monkeypatch):
    loaded = []

    class FakeModel:
        def __init__(self, path, **kwargs):
            loaded.append(path)
            assert kwargs == {
                "device": "cpu",
                "compute_type": "int8",
                "local_files_only": True,
            }

        def transcribe(self, audio, **kwargs):
            assert len(audio) == 3200  # Decoded and resampled from 8 to 16 kHz.
            assert abs(float(audio[100]) - 0.125) < 0.001
            assert kwargs["language"] == "en"
            return iter(
                [SimpleNamespace(start=0.01, end=0.18, text=" Hello world. ")]
            ), SimpleNamespace(language="en")

    monkeypatch.setattr(faster_whisper, "WhisperModel", FakeModel)
    for _ in range(2):
        response = client.post("/v1/extract", json=request(language="en"))
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["request_id"] == "test"
        assert result["document_metadata"]["duration_seconds"] == 0.2
        assert result["segments"][0]["text"] == "Hello world."
        assert result["segments"][0]["source_origin"] == {
            "start_seconds": 0.01,
            "end_seconds": 0.18,
            "model": "approved-whisper-base",
        }
    assert len(loaded) == 1


def test_missing_model_reports_unready_without_downloading(monkeypatch):
    monkeypatch.setenv("OSII_WHISPER_MODEL_DIR", "not-a-staged-directory")
    with TestClient(main.app) as client:
        assert client.get("/ready").status_code == 503
        assert client.post("/v1/extract", json=request()).status_code == 503


@pytest.mark.parametrize(
    ("payload", "status"),
    [
        (request(filename="file.pdf"), 415),
        (request(raw=b"not audio"), 422),
        (request(language="English"), 422),
        (request(model_path="not-a-request-setting"), 422),
    ],
)
def test_rejects_unsupported_input(client, payload, status):
    assert client.post("/v1/extract", json=payload).status_code == status


def test_rejects_long_decoded_audio_before_model_load(client, monkeypatch):
    monkeypatch.setattr(main, "MAX_SECONDS", 1)
    assert client.post("/v1/extract", json=request(raw=wav(16_000))).status_code == 413
