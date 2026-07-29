"""Demo UI and tuning routes."""

from __future__ import annotations

from pathlib import Path

import cv2
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.core.pipeline import detect_page_regions, ocr_page_regions
from app.defaults import DEFAULT_PARAMS
from app.demo.schemas import DemoDetectRequest, DemoOCRRequest
from app.demo.storage import storage

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@router.get("/demo", response_class=HTMLResponse)
async def demo_page(request: Request):
    """Render the demo page.

    Parameters
    ----------
    request : Request
        FastAPI request object.

    Returns
    -------
    HTMLResponse
        Rendered demo page.
    """
    return templates.TemplateResponse(
        "demo.html",
        {
            "request": request,
            "enable_demo": settings.enable_demo,
        },
    )


@router.get("/demo/config")
async def demo_config():
    """Return demo default configuration.

    Returns
    -------
    dict
        Default detection and recognition parameters.
    """
    return {"defaults": DEFAULT_PARAMS}


@router.post("/demo/upload")
async def demo_upload(file: UploadFile = File(...)):
    """Upload a PDF or image for demo analysis.

    Parameters
    ----------
    file : UploadFile
        Uploaded file.

    Returns
    -------
    JSONResponse
        Document metadata.
    """
    if file is None:
        raise HTTPException(status_code=400, detail="Missing file")

    file_bytes = await file.read()
    if not file_bytes:
        return JSONResponse(status_code=400, content={"error": "Empty file"})

    max_size_bytes = settings.demo_max_file_size_mb * 1024 * 1024
    if len(file_bytes) > max_size_bytes:
        return JSONResponse(
            status_code=400,
            content={"error": f"File exceeds {settings.demo_max_file_size_mb} MB limit"},
        )

    try:
        record = storage.create_document(
            file_bytes=file_bytes,
            filename=file.filename or "upload",
            dpi=settings.default_pdf_dpi,
        )
        return record
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.post("/demo/detect")
async def demo_detect(payload: DemoDetectRequest):
    """Run OpenCV region detection only.

    Parameters
    ----------
    payload : DemoDetectRequest
        Demo detect request.

    Returns
    -------
    JSONResponse
        Detection results with preview URLs and cached region set ID.
    """
    page_path = storage.get_page_path(payload.doc_id, payload.page)
    if not page_path.exists():
        return JSONResponse(status_code=404, content={"error": "Page not found"})

    image = cv2.imread(str(page_path))
    if image is None:
        return JSONResponse(status_code=500, content={"error": "Failed to load page image"})

    try:
        regions, debug, debug_images = detect_page_regions(
            image=image,
            params=payload.params,
            include_debug=True,
        )

        image_urls: dict[str, str] = {}
        for name, debug_image in debug_images.items():
            image_urls[name] = storage.save_preview(
                doc_id=payload.doc_id,
                page=payload.page,
                name=f"detect-{name}",
                image=debug_image,
            )

        stats = debug.metadata if debug else {}
        region_set_id = storage.save_region_set(
            doc_id=payload.doc_id,
            page=payload.page,
            params=payload.params.model_dump(),
            regions=regions,
            stats=stats,
        )

        return {
            "doc_id": payload.doc_id,
            "page": payload.page,
            "region_set_id": region_set_id,
            "images": image_urls,
            "regions": regions,
            "stats": stats,
        }
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.post("/demo/ocr")
async def demo_ocr(payload: DemoOCRRequest):
    """Run Tesseract on a cached region set.

    Parameters
    ----------
    payload : DemoOCRRequest
        Demo OCR request.

    Returns
    -------
    JSONResponse
        OCR results and preview URLs.
    """
    page_path = storage.get_page_path(payload.doc_id, payload.page)
    if not page_path.exists():
        return JSONResponse(status_code=404, content={"error": "Page not found"})

    image = cv2.imread(str(page_path))
    if image is None:
        return JSONResponse(status_code=500, content={"error": "Failed to load page image"})

    try:
        region_payload = storage.load_region_set(
            doc_id=payload.doc_id,
            page=payload.page,
            region_set_id=payload.region_set_id,
        )
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"error": "Region set not found"})

    try:
        run, debug_images = ocr_page_regions(
            image=image,
            regions=region_payload["regions"],
            detection_params=payload.detection_params,
            recognition_params=payload.recognition_params,
            include_debug=True,
        )

        image_urls: dict[str, str] = {}
        for name, debug_image in debug_images.items():
            image_urls[name] = storage.save_preview(
                doc_id=payload.doc_id,
                page=payload.page,
                name=f"ocr-{name}",
                image=debug_image,
            )

        metadata = run.debug.metadata if run.debug else {}
        return {
            "doc_id": payload.doc_id,
            "page": payload.page,
            "region_set_id": payload.region_set_id,
            "images": image_urls,
            "results": run.results,
            "stats": metadata,
        }
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.get("/demo/assets/{doc_id}/{subdir}/{filename}")
async def demo_assets(doc_id: str, subdir: str, filename: str):
    """Serve demo asset files.

    Parameters
    ----------
    doc_id : str
        Document identifier.
    subdir : str
        Asset subdirectory.
    filename : str
        File name.

    Returns
    -------
    FileResponse
        Static file response.
    """
    if subdir not in {"pages", "previews"}:
        raise HTTPException(status_code=404, detail="Asset not found")

    path = storage.get_doc_dir(doc_id) / subdir / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Asset not found")

    return FileResponse(path)