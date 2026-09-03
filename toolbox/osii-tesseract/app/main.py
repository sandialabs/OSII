"""Application entry point."""

from __future__ import annotations

from pathlib import Path

from fastapi.staticfiles import StaticFiles
from osii_processor_sdk import create_processor_app

from app.api.ocr import router as ocr_router
from app.config import settings
from app.processor import TesseractRegionExtractor


def create_app():
    """Create and configure the FastAPI application.

    Returns
    -------
    FastAPI
        Configured application instance.
    """
    application = create_processor_app(TesseractRegionExtractor())

    application.include_router(ocr_router)

    if settings.enable_demo:
        from app.demo.router import router as demo_router

        application.include_router(demo_router)
        application.mount(
            "/demo/static",
            StaticFiles(directory=str(Path(__file__).parent / "demo" / "static")),
            name="demo-static",
        )

    return application


app = create_app()
