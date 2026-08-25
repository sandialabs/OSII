import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from osii.api.collection_synthesis_routes import router as collection_synthesis_router
from osii.api.catalog_routes import router as catalog_router
from osii.api.chat_routes import router as chat_router
from osii.api.collections_routes import router as collections_router
from osii.api.embedding_routes import router as embedding_router
from osii.api.enrichment_jobs_routes import router as enrichment_jobs_router
from osii.api.enrichments_routes import router as enrichments_router
from osii.api.extractor_routes import router as extractor_router
from osii.api.extraction_variants_routes import router as extraction_variants_router
from osii.api.folder_synthesizer_routes import router as folder_synthesizer_router
from osii.api.intake_routes import router as intake_router
from osii.api.keyword_sets_routes import router as keyword_sets_router
from osii.api.objects_routes import router as objects_router
from osii.api.packages_routes import router as packages_router
from osii.api.osii_read_routes import router as osii_read_router
from osii.api.osii_routes import router as osii_router
from osii.api.extractor_routes import router as extractor_routes_router
from osii.api.extractors import router as extractors_router
from osii.api.preview_routes import router as preview_router
from osii.api.processors_routes import router as processors_router
from osii.api.processor_admin_routes import router as processor_admin_router
from osii.api.processor_settings_routes import router as processor_settings_router
from osii.api.model_provider_routes import router as model_provider_router
from osii.api.runs_routes import router as runs_router
from osii.api.scopes_routes import router as scopes_router
from osii.api.search_routes import router as search_router
from osii.api.synthesis_routes import router as synthesis_router
from osii.api.synthesizer_routes import router as synthesizer_router
from osii.api.text_routes import router as text_router
from osii.domain.processing.jobs import configure_job_store
from osii.domain.catalog_db import ensure_catalog

app = FastAPI(
    title="OSII Backend",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    )

app.state.shared_volume_root = Path(
    os.getenv("SHARED_VOLUME_ROOT", "./data_volume/my_data")
).resolve()
app.state.shared_volume_host_path = os.getenv("SHARED_VOLUME_HOST_PATH", "").strip()

app.state.osii_root = Path(
    os.getenv("OSII_ROOT", "./data_volume/.osii")
).resolve()
app.state.osii_root.mkdir(parents=True, exist_ok=True)

app.state.upload_originals_root = Path(
    os.getenv("UPLOAD_ORIGINALS_ROOT", "./data_volume/uploaded_data")
).resolve()
app.state.upload_originals_root.mkdir(parents=True, exist_ok=True)
configure_job_store(app.state.osii_root)
ensure_catalog(app.state.osii_root)

app.include_router(intake_router)
app.include_router(runs_router)
app.include_router(osii_router)
app.include_router(osii_read_router)
app.include_router(extractor_routes_router)
app.include_router(extractors_router)
app.include_router(preview_router)
app.include_router(extractor_router)
app.include_router(extraction_variants_router)
app.include_router(synthesizer_router)
app.include_router(folder_synthesizer_router)
app.include_router(embedding_router)
app.include_router(search_router)
app.include_router(scopes_router)
app.include_router(objects_router)
app.include_router(packages_router)
app.include_router(keyword_sets_router)
app.include_router(collections_router)
app.include_router(collection_synthesis_router)
app.include_router(catalog_router)
app.include_router(enrichments_router)
app.include_router(text_router)
app.include_router(synthesis_router)
app.include_router(enrichment_jobs_router)
app.include_router(processors_router)
app.include_router(processor_admin_router)
app.include_router(processor_settings_router)
app.include_router(model_provider_router)
app.include_router(chat_router)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/artifact/{file_path:path}", name="download_artifact")
async def download_artifact(file_path: str):
    target = (app.state.osii_root / file_path).resolve()
    osii_root = app.state.osii_root.resolve()

    try:
        target.relative_to(osii_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid artifact path") from exc

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")

    return FileResponse(target)


@app.get("/")
async def root():
    return {"message": "AI Ready Ingest OSII Core Backend"}
