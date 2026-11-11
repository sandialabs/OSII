"""Tests for the optional OSII processor adapter."""

import base64
import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from osii.processor_sdk import DocumentInput, ExtractionRequest

from banyan_extract.integrations import osii_extractor
from banyan_extract.integrations.osii_extractor import BanyanOsiiExtractor, app


def test_osii_extractor_preserves_element_bounding_box_provenance(monkeypatch):
    """OSII segments and artifacts retain the complete Nemotron bbox response."""
    response_output = SimpleNamespace(
        bboxdata=[[
            {
                "type": "Text",
                "text": "Grounded text",
                "bbox": {"xmin": 0.1, "ymin": 0.2, "xmax": 0.8, "ymax": 0.3},
            },
        ]],
    )
    processor = SimpleNamespace(process_document=lambda _path, **_kwargs: response_output)
    extractor = BanyanOsiiExtractor()
    monkeypatch.setattr(extractor, "_processor", lambda _config: processor)
    request = ExtractionRequest(
        request_id="test-request",
        document=DocumentInput(
            filename="document.pdf",
            media_type="application/pdf",
            content_base64=base64.b64encode(b"%PDF-test").decode("ascii"),
        ),
    )

    result = extractor.extract(request)

    assert result.segments[0].source_origin["page"] == 1
    assert result.segments[0].source_origin["bbox"]["xmin"] == 0.1
    assert result.artifacts[0].kind == "banyan_bounding_boxes"
    assert result.artifacts[0].json_data["pages"][0]["elements"] == response_output.bboxdata[0]


def extraction_request(filename="document.pdf", content=b"%PDF-test"):
    return ExtractionRequest(
        request_id="adapter-test",
        document=DocumentInput(filename=filename, content_base64=base64.b64encode(content).decode("ascii")),
    )


def test_health_and_descriptor_work_without_endpoint(monkeypatch):
    monkeypatch.setattr(osii_extractor, "get_nemoparse_config", lambda _path: {})
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        descriptor = client.get("/v1/descriptor").json()
    assert descriptor["name"] == "banyan.nemotron-parse"
    assert ".pdf" in descriptor["capabilities"]["file_extensions"]


def test_missing_endpoint_returns_actionable_error(monkeypatch):
    monkeypatch.setattr(osii_extractor, "get_nemoparse_config", lambda _path: {
        "NEMOPARSE_ENDPOINT": "", "NEMOPARSE_MODEL": "nemotron", "NEMOPARSE_API_KEY": "",
    })
    with TestClient(app) as client:
        result = client.post("/v1/extract", json=extraction_request().model_dump())
    assert result.status_code == 422
    assert "NEMOPARSE_ENDPOINT" in result.json()["detail"]


@pytest.mark.parametrize("filename,encoded", [
    ("file.exe", "YWJj"), ("file.pdf", None), ("file.pdf", "%%%"),
])
def test_invalid_input_is_rejected_before_model_call(monkeypatch, filename, encoded):
    extractor = BanyanOsiiExtractor()
    monkeypatch.setattr(extractor, "_processor", lambda _config: pytest.fail("Unexpected model access"))
    request = extraction_request(filename)
    request.document.content_base64 = encoded
    with pytest.raises(ValueError):
        extractor.extract(request)


@pytest.mark.parametrize("fails", [False, True])
def test_request_files_are_isolated_and_removed(monkeypatch, fails):
    seen_paths = []

    def process(path, **kwargs):
        seen_paths.append(Path(path))
        assert Path(path).read_bytes() == b"%PDF-test"
        assert kwargs == {"overwrite": True, "draw_bboxes": False}
        if fails:
            raise RuntimeError("Model unavailable")
        return SimpleNamespace(bboxdata=[[]])

    extractor = BanyanOsiiExtractor()
    monkeypatch.setattr(extractor, "_processor", lambda _config: SimpleNamespace(process_document=process))
    if fails:
        with pytest.raises(RuntimeError, match="Model unavailable"):
            extractor.extract(extraction_request())
    else:
        assert extractor.extract(extraction_request()).warnings
    assert seen_paths and not seen_paths[0].parent.exists()


def test_local_configuration_uses_tool_directory_and_environment(monkeypatch, tmp_path):
    from banyan_extract.utils.setup_nemoparse_config import get_nemoparse_config

    settings = tmp_path / "settings.env"
    settings.write_text('NEMOPARSE_ENDPOINT="http://file-endpoint/v1"\nNEMOPARSE_MODEL="file-model"\n')
    monkeypatch.setenv("NEMOPARSE_ENDPOINT", "http://environment-endpoint/v1")
    monkeypatch.delenv("NEMOPARSE_MODEL", raising=False)
    assert get_nemoparse_config(settings)["NEMOPARSE_ENDPOINT"] == "http://environment-endpoint/v1"
    assert get_nemoparse_config(settings)["NEMOPARSE_MODEL"] == "file-model"

    def read_config(path):
        assert path == Path(osii_extractor.__file__).resolve().parents[3] / ".env"
        return {"NEMOPARSE_ENDPOINT": "http://local-endpoint/v1", "NEMOPARSE_MODEL": "local-model",
                "NEMOPARSE_API_KEY": "test-key"}

    monkeypatch.setattr(osii_extractor, "get_nemoparse_config", read_config)
    monkeypatch.setattr(osii_extractor, "NemoparseProcessor", lambda **kwargs: kwargs)
    monkeypatch.chdir(tmp_path)
    config = BanyanOsiiExtractor()._processor({})
    assert config["endpoint_url"] == "http://local-endpoint/v1"
    assert config["api_key"] == "test-key"


def test_http_extraction_runs_banyan_pipeline_with_mocked_nemotron(monkeypatch):
    monkeypatch.setenv("NEMOPARSE_ENDPOINT", "http://unused-test-endpoint/v1")
    monkeypatch.setenv("NEMOPARSE_MODEL", "test-model")
    elements = [{"type": "Text", "text": "Corporate document text",
                 "bbox": {"xmin": 0.1, "ymin": 0.2, "xmax": 0.8, "ymax": 0.3}}]
    monkeypatch.setattr(
        "banyan_extract.ocr.nemotron_ocr.NemotronOCR.get_detailed_ocr_results",
        lambda *_args, **_kwargs: elements,
    )
    image = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(image, format="PNG")
    with TestClient(app) as client:
        response = client.post("/v1/extract", json=extraction_request("document.png", image.getvalue()).model_dump())
    assert response.status_code == 200
    result = response.json()
    assert result["segments"][0]["text"] == "Corporate document text"
    assert result["artifacts"][0]["json_data"]["pages"][0]["elements"] == elements
