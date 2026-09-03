from __future__ import annotations

import base64

import pytest

from app.core.models import DocumentPageResult
from app.processor import TesseractRegionExtractor
from osii_processor_sdk import DocumentInput, ExtractionRequest


def test_processor_api_preserves_region_geometry(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.processor.process_document_bytes",
        lambda **_kwargs: [
            DocumentPageResult(
                page_number=2,
                width=1000,
                height=1400,
                results=[
                    {
                        "text": "Grounded OCR text",
                        "bbox": [0.1, 0.2, 0.7, 0.3],
                        "polygon": [[0.1, 0.2], [0.7, 0.2], [0.7, 0.3], [0.1, 0.3]],
                        "confidence": 0.96,
                    }
                ],
            )
        ],
    )

    response = TesseractRegionExtractor().extract(
        ExtractionRequest(
            request_id="ocr-1",
            document=DocumentInput(
                filename="scan.pdf",
                media_type="application/pdf",
                content_base64=base64.b64encode(b"placeholder").decode(),
            ),
        )
    )

    assert response.processor.name == "toolchest.tesseract-opencv"
    assert response.segments[0].id == "page-2-region-1"
    assert response.segments[0].source_origin == {
        "page": 2,
        "bbox": [0.1, 0.2, 0.7, 0.3],
        "polygon": [[0.1, 0.2], [0.7, 0.2], [0.7, 0.3], [0.1, 0.3]],
        "confidence": 0.96,
        "coordinate_space": "normalized-page",
        "page_width": 1000,
        "page_height": 1400,
    }


def test_processor_api_rejects_unknown_ocr_configuration() -> None:
    request = ExtractionRequest(
        request_id="ocr-2",
        document=DocumentInput(
            filename="scan.pdf",
            content_base64=base64.b64encode(b"placeholder").decode(),
        ),
        config={"unknown": True},
    )

    with pytest.raises(ValueError, match="Unsupported OCR configuration"):
        TesseractRegionExtractor().extract(request)
