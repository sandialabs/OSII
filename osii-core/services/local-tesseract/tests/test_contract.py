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
        return f"Text from page {len(calls)}"

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


def test_invalid_payload_and_unknown_config_are_422():
    assert client.post("/v1/extract", json={}).status_code == 422
    request = _request()
    request["config"] = {"opencv_threshold": 123}
    response = client.post("/v1/extract", json=request)
    assert response.status_code == 422
    assert "Unsupported Tesseract configuration" in response.json()["detail"]
