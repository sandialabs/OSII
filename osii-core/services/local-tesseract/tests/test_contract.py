from __future__ import annotations

import base64

from fastapi.testclient import TestClient
import pymupdf

from app import main


client = TestClient(main.app)


def _pdf_with_two_pages() -> bytes:
    document = pymupdf.open()
    document.new_page()
    document.new_page()
    value = document.tobytes()
    document.close()
    return value


def _request() -> dict:
    return {
        "request_id": "ocr-1",
        "document": {
            "file_id": "file-1",
            "filename": "scanned.pdf",
            "media_type": "application/pdf",
            "content_base64": base64.b64encode(_pdf_with_two_pages()).decode(),
        },
    }


def test_contract_and_page_provenance(monkeypatch):
    calls = []

    def fake_ocr(image, *, language, dpi, page_segmentation_mode):
        calls.append((image, language, dpi, page_segmentation_mode))
        return {"text": f"Text from page {len(calls)}", "regions": [{"text": "Text", "bbox": [0.1, 0.2, 0.4, 0.3], "confidence": 0.9, "char_start": 0, "char_end": 4}], "page_width": 1000, "page_height": 1400}

    monkeypatch.setattr(main, "_ocr_page", fake_ocr)

    assert client.get("/health").json() == {"status": "ok"}
    descriptor = client.get("/v1/descriptor").json()
    assert descriptor["name"] == "local.tesseract-page-ocr"
    assert "OpenCV" in descriptor["description"]
    assert "/v1/extract" in client.get("/openapi.json").json()["paths"]

    response = client.post("/v1/extract", json=_request())

    assert response.status_code == 200
    body = response.json()
    assert [segment["id"] for segment in body["segments"]] == ["page-1", "page-2"]
    assert body["segments"][1]["source_origin"]["page"] == 2
    assert body["document_metadata"]["ocr_mode"] == "full_page"
    assert len(calls) == 2
    assert body["segments"][0]["source_origin"]["regions"][0]["bbox"] == [0.1, 0.2, 0.4, 0.3]
    assert body["segments"][0]["source_origin"]["coordinate_space"] == "normalized-page"


def test_invalid_payload_and_unknown_config_are_422():
    assert client.post("/v1/extract", json={}).status_code == 422
    request = _request()
    request["config"] = {"opencv_threshold": 123}
    response = client.post("/v1/extract", json=request)
    assert response.status_code == 422
    assert "Unsupported Tesseract configuration" in response.json()["detail"]


def test_readiness_distinguishes_missing_native_ocr_from_http_liveness(monkeypatch):
    monkeypatch.setattr(main.shutil, 'which', lambda _: None)
    assert client.get('/health').status_code==200
    assert client.get('/ready').status_code==503
    monkeypatch.setattr(main.shutil, 'which', lambda _: '/synthetic/tesseract')
    assert client.get('/ready').json()['status']=='ready'


def test_tsv_retains_word_confidence_boxes_and_exact_text_offsets():
    value = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
    value += "1\t1\t0\t0\t0\t0\t0\t0\t1000\t2000\t-1\t\n"
    value += "5\t1\t1\t1\t1\t1\t100\t200\t150\t50\t96.5\tHello\n"
    value += "5\t1\t1\t1\t1\t2\t270\t200\t130\t50\t0\tworld\n"
    value += "5\t1\t1\t1\t2\t1\t100\t300\t80\t50\t-1\tNext\n"
    result = main._parse_tsv(value)
    assert result["text"] == "Hello world\nNext"
    assert result["regions"][0]["bbox"] == [0.1, 0.1, 0.25, 0.125]
    assert result["regions"][0]["confidence"] == 0.965
    assert result["regions"][1]["confidence"] == 0
    assert "confidence" not in result["regions"][2]
    for region in result["regions"]:
        assert result["text"][region["char_start"]:region["char_end"]] == region["text"]


def test_ocr_invokes_tsv_output_with_native_program(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(main.shutil, "which", lambda _: "/native/tesseract")
    calls = []
    def run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        return SimpleNamespace(returncode=0, stdout=b"level\ttext\n", stderr=b"")
    monkeypatch.setattr(main.subprocess, "run", run)
    assert main._ocr_page(b"image", language="eng", dpi=200, page_segmentation_mode=3)["text"] == ""
    assert calls[0][0][-1] == "tsv"


def test_tesseract_page_timeout_is_actionable(monkeypatch):
    import subprocess
    monkeypatch.setattr(main.shutil, "which", lambda _: "/native/tesseract")
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("tesseract", 180)
    monkeypatch.setattr(main.subprocess, "run", timeout)
    import pytest
    with pytest.raises(ValueError, match="timed out.*no partial extraction"):
        main._ocr_page(b"image", language="eng", dpi=200, page_segmentation_mode=3)
