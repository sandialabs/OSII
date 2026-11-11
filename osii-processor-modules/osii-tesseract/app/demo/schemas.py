"""Demo request and response schemas."""

from __future__ import annotations

from pydantic import BaseModel

from app.core.models import DetectionParams, RecognitionParams


class DemoDetectRequest(BaseModel):
    """Demo detect request."""

    doc_id: str
    page: int
    params: DetectionParams


class DemoOCRRequest(BaseModel):
    """Demo OCR request."""

    doc_id: str
    page: int
    region_set_id: str
    detection_params: DetectionParams
    recognition_params: RecognitionParams