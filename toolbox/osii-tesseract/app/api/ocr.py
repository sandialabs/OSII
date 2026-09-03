"""Production OCR API routes."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.core.models import OCRParams
from app.core.pipeline import process_document_bytes, process_image_bytes

router = APIRouter()


@router.post("/ocr")
async def ocr_endpoint(
    file: UploadFile = File(...),
    language: str = Form("en"),
):
    """Run OCR on a single image and return LiteParse-compatible output.

    Parameters
    ----------
    file : UploadFile
        Uploaded image file.
    language : str
        ISO 639-1 language code.

    Returns
    -------
    dict
        LiteParse-compatible OCR response.
    """
    if file is None:
        raise HTTPException(status_code=400, detail="Missing file")

    try:
        file_bytes = await file.read()
        if not file_bytes:
            return JSONResponse(status_code=400, content={"error": "Empty file"})

        params = OCRParams(language=language)
        run = process_image_bytes(
            file_bytes=file_bytes,
            filename=file.filename or "upload",
            params=params,
            include_debug=False,
        )
        return {"results": run.results}
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.post("/ocr/document")
async def ocr_document_endpoint(
    file: UploadFile = File(...),
    language: str = Form("en"),
):
    """Run OCR on an image or PDF and return per-page results.

    Parameters
    ----------
    file : UploadFile
        Uploaded image or PDF.
    language : str
        ISO 639-1 language code.

    Returns
    -------
    dict
        Per-page OCR results.
    """
    if file is None:
        raise HTTPException(status_code=400, detail="Missing file")

    try:
        file_bytes = await file.read()
        if not file_bytes:
            return JSONResponse(status_code=400, content={"error": "Empty file"})

        params = OCRParams(language=language)
        pages = process_document_bytes(
            file_bytes=file_bytes,
            filename=file.filename or "upload",
            params=params,
            include_debug=False,
        )

        return {
            "pages": [
                {
                    "page": page.page_number,
                    "width": page.width,
                    "height": page.height,
                    "results": page.results,
                }
                for page in pages
            ]
        }
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})