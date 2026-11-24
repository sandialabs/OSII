"""Local, opt-in OCRia-nano-1 extraction. Model installation is operator-owned."""

from __future__ import annotations

import base64
import io
import math
import os
from pathlib import Path
from threading import Lock

import liteparse
import pymupdf
from fastapi import HTTPException
from liteparse import LiteParse, ParseError, ParseTimeoutError, models
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
from PIL import Image, ImageOps

MODEL = "ocria-nano"
EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg"]
MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 25
MAX_PIXELS = 24_000_000
DPI = 250


def installed_model() -> models.InstalledModel:
    if os.getenv("OSII_OCRIA_LICENSE_ACKNOWLEDGED", "").strip().lower() != "true":
        raise HTTPException(
            503,
            "Review the separate OCRia-nano-1 Model License. If your use is authorized, set OSII_OCRIA_LICENSE_ACKNOWLEDGED=true.",
        )
    try:
        for package in models.list():
            if package.name == MODEL and package.complete:
                return package
    except (OSError, RuntimeError):
        pass
    raise HTTPException(
        503, "OCRia-nano is not staged. See the module README for manual installation."
    )


def pdf_bytes(raw: bytes, suffix: str) -> tuple[bytes, int]:
    try:
        if suffix == ".pdf":
            with pymupdf.open(stream=raw, filetype="pdf") as pdf:
                if not raw.startswith(b"%PDF-") or pdf.needs_pass or not pdf.page_count:
                    raise HTTPException(
                        422, "Provide a non-empty PDF without a password."
                    )
                if pdf.page_count > MAX_PAGES:
                    raise HTTPException(
                        413, "Split PDFs into parts of at most 25 pages."
                    )
                for page in pdf:
                    w, h = page.rect.width * DPI / 72, page.rect.height * DPI / 72
                    if not (
                        0 < w <= 10_000
                        and 0 < h <= 10_000
                        and math.ceil(w) * math.ceil(h) <= MAX_PIXELS
                    ):
                        raise HTTPException(
                            413, "PDF page exceeds the OCR rendering size limit."
                        )
                return raw, pdf.page_count

        with Image.open(io.BytesIO(raw), formats=["PNG", "JPEG"]) as image:
            if image.width * image.height > MAX_PIXELS or max(image.size) > 10_000:
                raise HTTPException(
                    413,
                    "Resize the image to at most 24 megapixels and 10,000 pixels per side.",
                )
            if getattr(image, "n_frames", 1) != 1:
                raise HTTPException(422, "Supply a still image.")
            oriented = ImageOps.exif_transpose(image).convert("RGBA")
            flat = Image.new("RGB", oriented.size, "white")
            flat.paste(oriented, mask=oriented.getchannel("A"))
            encoded = io.BytesIO()
            flat.save(encoded, format="PNG")
            with pymupdf.open() as pdf:
                page = pdf.new_page(
                    width=flat.width * 72 / DPI, height=flat.height * 72 / DPI
                )
                page.insert_image(page.rect, stream=encoded.getvalue())
                return pdf.tobytes(), 1
    except (ValueError, OSError, RuntimeError, Image.DecompressionBombError):
        raise HTTPException(
            422, "LiteParse could not read the supplied PDF or image."
        ) from None


class OcriaExtractor(Extractor):
    descriptor = ProcessorDescriptor(
        name="local.ocria-nano",
        version="0.1.0",
        kind=ProcessorKind.EXTRACTOR,
        display_name="OCRia-nano-1 via LiteParse",
        description="Local CPU OCR for PDFs and scans. The OCRia model has a separate, restricted license.",
        capabilities=Capability(file_extensions=EXTENSIONS, output_kinds=["text"]),
    )

    def __init__(self):
        self._busy = Lock()

    def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        suffix = Path(request.document.filename).suffix.lower()
        if suffix not in EXTENSIONS:
            raise HTTPException(415, "Choose a PDF, PNG or JPEG file.")
        if request.config:
            raise HTTPException(422, "OCRia does not accept per-request model options.")
        encoded = request.document.content_base64
        if not encoded:
            raise HTTPException(422, "Supply the file bytes as content_base64.")
        if len(encoded) > 4 * ((MAX_BYTES + 2) // 3):
            raise HTTPException(413, "The input exceeds 20 MiB.")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except ValueError:
            raise HTTPException(422, "Source bytes must be valid Base64.") from None
        if len(raw) > MAX_BYTES:
            raise HTTPException(413, "The input exceeds 20 MiB.")
        if not self._busy.acquire(blocking=False):
            raise HTTPException(429, "OCRia is already processing a document.")
        try:
            package = installed_model()
            pdf, page_count = pdf_bytes(raw, suffix)
            with LiteParse(
                ocr_backend=MODEL,
                output_format="markdown",
                dpi=DPI,
                max_pages=MAX_PAGES,
                num_workers=1,
                pool_size=1,
                parse_timeout=90,
                image_mode="off",
                extract_images=False,
                extract_links=False,
                continue_on_page_error=False,
                ocr_failure_fatal=True,
                quiet=True,
            ) as parser:
                result = parser.parse(pdf)
        except ParseTimeoutError:
            raise HTTPException(504, "OCRia timed out. Try fewer pages.") from None
        except (ParseError, OSError, RuntimeError, ValueError):
            raise HTTPException(
                422,
                "LiteParse with OCRia could not finish extraction. Check the input and staged runtime.",
            ) from None
        finally:
            self._busy.release()
        if result.page_errors or [page.page_num for page in result.pages] != list(
            range(1, page_count + 1)
        ):
            raise HTTPException(
                422, "LiteParse did not return every page; no partial result was saved."
            )
        segments = []
        for page in result.pages:
            markdown = page.markdown.strip()
            text = markdown or page.text.strip()
            if text:
                segments.append(
                    TextSegment(
                        id=f"page-{page.page_num:04d}",
                        text=text,
                        segment_type="markdown" if markdown else "text",
                        source_origin={"page": page.page_num, "engine": MODEL},
                    )
                )
        if not segments:
            raise HTTPException(422, "OCRia did not return readable text.")
        return ExtractionResponse(
            request_id=request.request_id,
            processor=self.descriptor,
            segments=segments,
            document_metadata={
                "model": "OCRia-nano-1",
                "model_package_version": package.version or "unknown",
                "liteparse_version": liteparse.__version__,
                "pages": page_count,
            },
        )


app = create_processor_app(OcriaExtractor())


@app.get("/ready")
def ready():
    package = installed_model()
    return {"status": "ok", "model": "OCRia-nano-1", "version": package.version}
