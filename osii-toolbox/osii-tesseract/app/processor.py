"""OSII Processor API v1 adapter for the region-aware OCR pipeline."""

from __future__ import annotations

import base64

from osii_processor_sdk import (
    Capability,
    ExtractionRequest,
    ExtractionResponse,
    Extractor,
    ProcessorDescriptor,
    ProcessorKind,
    TextSegment,
)

from app.core.models import OCRParams
from app.core.pipeline import process_document_bytes


OCR_CONFIG_PROPERTIES = {
    "language": {"type": "string", "default": "en"},
    "confidence_threshold": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.5},
    "threshold_mode": {"type": "string", "enum": ["adaptive", "otsu"], "default": "adaptive"},
    "blur_kernel": {"type": "integer", "minimum": 1, "maximum": 21, "default": 3},
    "adaptive_block_size": {"type": "integer", "minimum": 3, "maximum": 101, "default": 31},
    "adaptive_c": {"type": "integer", "minimum": -100, "maximum": 100, "default": 15},
    "open_kernel_w": {"type": "integer", "minimum": 1, "maximum": 20, "default": 4},
    "open_kernel_h": {"type": "integer", "minimum": 1, "maximum": 20, "default": 2},
    "dilate_kernel_w": {"type": "integer", "minimum": 1, "maximum": 100, "default": 30},
    "dilate_kernel_h": {"type": "integer", "minimum": 1, "maximum": 100, "default": 30},
    "dilate_iterations": {"type": "integer", "minimum": 1, "maximum": 10, "default": 1},
    "min_contour_area": {"type": "integer", "minimum": 0, "maximum": 500000, "default": 50},
    "min_width": {"type": "integer", "minimum": 0, "maximum": 10000, "default": 10},
    "min_height": {"type": "integer", "minimum": 0, "maximum": 10000, "default": 8},
    "bbox_padding": {"type": "integer", "minimum": 0, "maximum": 200, "default": 4},
    "max_regions": {"type": "integer", "minimum": 1, "maximum": 5000, "default": 200},
    "tesseract_psm": {"type": "string", "enum": ["auto", "6", "7", "8", "11", "13"], "default": "auto"},
}


class TesseractRegionExtractor(Extractor):
    """Return one grounded segment for each OCR region on each source page."""

    descriptor = ProcessorDescriptor(
        name="toolchest.tesseract-opencv",
        version="0.2.0",
        display_name="Tesseract OCR with OpenCV regions",
        description=(
            "Detects candidate text regions with OpenCV, runs Tesseract on each "
            "region, and returns text with normalized page bounding boxes."
        ),
        kind=ProcessorKind.EXTRACTOR,
        capabilities=Capability(
            media_types=["application/pdf", "image/png", "image/jpeg", "image/tiff"],
            file_extensions=[".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"],
        ),
        config_schema={
            "type": "object",
            "properties": OCR_CONFIG_PROPERTIES,
            "additionalProperties": False,
        },
    )

    def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        encoded = request.document.content_base64
        if not encoded:
            raise ValueError("document.content_base64 is required for OCR")
        try:
            source_bytes = base64.b64decode(encoded, validate=True)
        except ValueError as exc:
            raise ValueError("document.content_base64 is not valid base64") from exc

        unknown_options = set(request.config) - set(OCR_CONFIG_PROPERTIES)
        if unknown_options:
            raise ValueError(f"Unsupported OCR configuration: {', '.join(sorted(unknown_options))}")
        supported_options = set(OCRParams.model_fields)
        options = {key: value for key, value in request.config.items() if key in supported_options}
        params = OCRParams(**options)
        confidence_threshold = float(request.config.get("confidence_threshold", 0.5))
        if not 0 <= confidence_threshold <= 1:
            raise ValueError("confidence_threshold must be between 0 and 1")

        pages = process_document_bytes(
            file_bytes=source_bytes,
            filename=request.document.filename,
            params=params,
        )
        segments: list[TextSegment] = []
        for page in pages:
            for region_number, result in enumerate(page.results, start=1):
                text = str(result.get("text") or "").strip()
                confidence = float(result.get("confidence") or 0)
                if not text or confidence < confidence_threshold:
                    continue
                segments.append(
                    TextSegment(
                        id=f"page-{page.page_number}-region-{region_number}",
                        text=text,
                        segment_type="ocr_region",
                        source_origin={
                            "page": page.page_number,
                            "bbox": result.get("bbox"),
                            "polygon": result.get("polygon"),
                            "confidence": confidence,
                            "coordinate_space": "normalized-page",
                            "page_width": page.width,
                            "page_height": page.height,
                        },
                    )
                )

        return ExtractionResponse(
            request_id=request.request_id,
            processor=self.descriptor,
            segments=segments,
            document_metadata={
                "page_count": len(pages),
                "coordinate_space": "normalized-page",
            },
            warnings=[] if segments else ["No OCR regions met the confidence threshold."],
        )
