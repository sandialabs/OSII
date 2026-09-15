from __future__ import annotations

import base64
from pathlib import Path
import shutil
import subprocess
from typing import Iterator

import pymupdf

from osii.processor_sdk import (
    Capability,
    ExtractionRequest,
    ExtractionResponse,
    Extractor,
    ProcessorDescriptor,
    ProcessorKind,
    TextSegment,
    create_processor_app,
)


SUPPORTED_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"]
SUPPORTED_LANGUAGES = ["eng", "fra", "deu", "spa", "jpn", "kor", "chi_sim", "ara"]


def _decode_document(request: ExtractionRequest) -> bytes:
    encoded = request.document.content_base64
    if not encoded:
        raise ValueError("document.content_base64 is required for Tesseract OCR")
    try:
        return base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise ValueError("document.content_base64 is not valid base64") from exc


def _render_pages(source: bytes, filename: str, dpi: int) -> Iterator[bytes]:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported Tesseract input format: {suffix or 'no extension'}")
    filetype = {
        ".jpg": "jpeg",
        ".tif": "tiff",
    }.get(suffix, suffix.removeprefix("."))
    try:
        with pymupdf.open(stream=source, filetype=filetype) as document:
            for page in document:
                yield page.get_pixmap(dpi=dpi, alpha=False).tobytes("png")
    except (RuntimeError, ValueError) as exc:
        raise ValueError(f"Could not open {filename} for page OCR: {exc}") from exc


def _ocr_page(
    image: bytes,
    *,
    language: str,
    dpi: int,
    page_segmentation_mode: int,
) -> str:
    executable = shutil.which("tesseract")
    if executable is None:
        raise ValueError(
            "Tesseract is not installed or is not on PATH. Install the native "
            "Tesseract program, then restart OSII."
        )
    completed = subprocess.run(
        [
            executable,
            "stdin",
            "stdout",
            "--dpi",
            str(dpi),
            "-l",
            language,
            "--psm",
            str(page_segmentation_mode),
        ],
        input=image,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()[-1000:]
        raise ValueError(f"Tesseract failed: {detail or f'exit code {completed.returncode}'}")
    return completed.stdout.decode("utf-8", errors="replace").strip()


class LocalTesseractPageExtractor(Extractor):
    """Run ordinary Tesseract once for each complete document page."""

    descriptor = ProcessorDescriptor(
        name="local.tesseract-page-ocr",
        version="1.0.0",
        display_name="Tesseract OCR — full page",
        description=(
            "Runs Tesseract on each complete PDF or image page and returns one "
            "grounded text segment per page. It does not use OpenCV region detection."
        ),
        kind=ProcessorKind.EXTRACTOR,
        capabilities=Capability(
            media_types=["application/pdf", "image/png", "image/jpeg", "image/tiff"],
            file_extensions=SUPPORTED_EXTENSIONS,
            output_kinds=["text_segments"],
        ),
        config_schema={
            "type": "object",
            "properties": {
                "language": {
                    "type": "string",
                    "enum": SUPPORTED_LANGUAGES,
                    "default": "eng",
                    "description": "Tesseract language data to use.",
                },
                "dpi": {
                    "type": "integer",
                    "minimum": 100,
                    "maximum": 400,
                    "default": 200,
                    "description": "Resolution used to render each PDF page.",
                },
                "page_segmentation_mode": {
                    "type": "integer",
                    "enum": [1, 3, 4, 6, 11, 12],
                    "default": 3,
                    "description": "Tesseract page segmentation mode; 3 is automatic.",
                },
            },
            "additionalProperties": False,
        },
    )

    def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        unknown = set(request.config) - {"language", "dpi", "page_segmentation_mode"}
        if unknown:
            raise ValueError(f"Unsupported Tesseract configuration: {', '.join(sorted(unknown))}")
        language = str(request.config.get("language", "eng"))
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported Tesseract language: {language}")
        dpi = int(request.config.get("dpi", 200))
        if not 100 <= dpi <= 400:
            raise ValueError("dpi must be between 100 and 400")
        page_segmentation_mode = int(request.config.get("page_segmentation_mode", 3))
        if page_segmentation_mode not in {1, 3, 4, 6, 11, 12}:
            raise ValueError("Unsupported Tesseract page segmentation mode")

        segments: list[TextSegment] = []
        blank_pages: list[int] = []
        page_count = 0
        pages = _render_pages(_decode_document(request), request.document.filename, dpi)
        for page_number, page_image in enumerate(pages, start=1):
            page_count = page_number
            text = _ocr_page(
                page_image,
                language=language,
                dpi=dpi,
                page_segmentation_mode=page_segmentation_mode,
            )
            if not text:
                blank_pages.append(page_number)
                continue
            segments.append(
                TextSegment(
                    id=f"page-{page_number}",
                    text=text,
                    segment_type="ocr_page",
                    source_origin={
                        "source_type": "ocr",
                        "unit_type": "page",
                        "page": page_number,
                        "ocr_engine": "tesseract",
                        "language": language,
                        "dpi": dpi,
                    },
                )
            )

        warnings = []
        if blank_pages:
            page_list = ", ".join(str(page) for page in blank_pages)
            warnings.append(f"Tesseract returned no text for page(s): {page_list}.")
        return ExtractionResponse(
            request_id=request.request_id,
            processor=self.descriptor,
            segments=segments,
            document_metadata={
                "page_count": page_count,
                "ocr_engine": "tesseract",
                "ocr_mode": "full_page",
                "language": language,
                "dpi": dpi,
            },
            warnings=warnings,
        )


app = create_processor_app(LocalTesseractPageExtractor())
