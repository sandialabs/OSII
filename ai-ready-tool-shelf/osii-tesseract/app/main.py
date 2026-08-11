"""Application entry point."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.ocr import router as ocr_router
from app.config import settings


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns
    -------
    FastAPI
        Configured application instance.
    """
    application = FastAPI(
        title="OSII-Tesseract",
        version="0.1.0",
    )

    application.include_router(ocr_router)

    @application.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

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
