from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from osii.domain.artifacts.artifact_staleness import get_artifact_staleness, mark_artifacts_stale
from osii.domain.artifacts.edited_text import (
    delete_edited_text,
    get_edited_text,
    put_edited_text_segments,
)
from osii.domain.artifacts.object_artifacts import get_object_artifact_summary
from osii.domain.artifacts.object_processing import get_object_processing_metadata
from osii.domain.artifacts.object_summaries import get_object_summaries
from osii.domain.artifacts.read_enrichments import list_scope_enrichments
from osii.domain.artifacts.source_files import get_source_file_path
from osii.domain.artifacts.text_representations import (
    get_preferred_text_representation,
    list_text_representations,
)
from osii.domain.read.docs import get_doc_meta, get_doc_overview
from osii.domain.read.manifest import list_manifest_records
from osii.domain.read.segments import list_segments
from osii.domain.read.synthesis import get_synth_text, get_synth_toml, list_syntheses
from osii.domain.scopes.collections import list_collections_for_file

router = APIRouter(prefix="/api/objects", tags=["objects"])


@router.get("/{file_id}")
async def get_object(request: Request, file_id: str):
    osii_root = request.app.state.osii_root.resolve()

    meta = get_doc_meta(osii_root, file_id)
    if meta is None:
        return {"error": "unknown file_id"}

    overview = get_doc_overview(osii_root, file_id)
    processing = get_object_processing_metadata(osii_root, file_id)
    enrichments = list_scope_enrichments(
        osii_root,
        {"scope_type": "object", "file_id": file_id},
    )
    artifact_summary = get_object_artifact_summary(osii_root, file_id)

    return {
        "file_id": file_id,
        "meta": meta,
        "overview": overview,
        "collections": list_collections_for_file(osii_root, file_id),
        "processing": processing,
        "enrichments": enrichments,
        "artifact_summary": artifact_summary,
    }


@router.post("/summaries")
async def get_object_summaries_route(request: Request, payload: dict):
    osii_root = request.app.state.osii_root.resolve()

    file_ids = payload.get("file_ids", [])
    if not isinstance(file_ids, list):
        return {"error": "file_ids must be a list"}

    return {
        "summaries": get_object_summaries(osii_root, file_ids),
    }


@router.get("/{file_id}/source")
async def get_object_source(request: Request, file_id: str):
    osii_root = request.app.state.osii_root.resolve()
    shared_root = request.app.state.shared_volume_root.resolve()
    upload_root = request.app.state.upload_originals_root.resolve()

    source_path = get_source_file_path(
        osii_root,
        shared_root,
        upload_root,
        file_id,
    )
    if source_path is None:
        return {"error": "source file not found"}

    return FileResponse(source_path)


@router.get("/{file_id}/texts/edited")
async def get_object_edited_text(request: Request, file_id: str):
    osii_root = request.app.state.osii_root.resolve()

    result = get_edited_text(osii_root, file_id)
    if result is None:
        return {"error": "unknown file_id"}

    return result


@router.put("/{file_id}/texts/edited")
async def put_object_edited_text(request: Request, file_id: str, payload: dict):
    osii_root = request.app.state.osii_root.resolve()

    segments = payload.get("segments")
    if not isinstance(segments, list):
        return {"error": "segments must be a list"}

    try:
        result = put_edited_text_segments(osii_root, file_id, segments)
    except ValueError as exc:
        return {"error": str(exc)}

    if result is None:
        return {"error": "unknown file_id"}

    stale = mark_artifacts_stale(
        osii_root,
        file_id,
        embeddings=True,
        search_chunks=True,
    )

    return {
        **result,
        "stale": stale.get("stale", {}),
    }


@router.delete("/{file_id}/texts/edited")
async def delete_object_edited_text(request: Request, file_id: str):
    osii_root = request.app.state.osii_root.resolve()

    result = delete_edited_text(osii_root, file_id)
    if result is None:
        return {"error": "unknown file_id"}

    stale = mark_artifacts_stale(
        osii_root,
        file_id,
        embeddings=True,
        search_chunks=True,
    )

    return {
        **result,
        "stale": stale.get("stale", {}),
    }


@router.get("/{file_id}/manifest")
async def get_object_manifest(request: Request, file_id: str):
    osii_root = request.app.state.osii_root.resolve()
    return {
        "file_id": file_id,
        "records": list_manifest_records(osii_root, file_id),
    }


@router.get("/{file_id}/texts")
async def get_object_text_representations_route(request: Request, file_id: str):
    osii_root = request.app.state.osii_root.resolve()

    representations = list_text_representations(osii_root, file_id)
    if representations is None:
        return {"error": "unknown file_id"}

    return {
        "file_id": file_id,
        "representations": representations,
        "segments": list_segments(osii_root, file_id),
    }


@router.get("/{file_id}/texts/preferred")
async def get_object_preferred_text(request: Request, file_id: str):
    osii_root = request.app.state.osii_root.resolve()

    preferred = get_preferred_text_representation(osii_root, file_id)
    if preferred is None:
        return {"error": "unknown file_id or text not found"}

    return {
        "file_id": file_id,
        "representation": preferred["name"],
        "kind": preferred["kind"],
        "text": preferred["text"],
        "path": preferred["path"],
    }


@router.get("/{file_id}/syntheses")
async def get_object_syntheses(request: Request, file_id: str):
    osii_root = request.app.state.osii_root.resolve()
    return {
        "file_id": file_id,
        "current_text": get_synth_text(osii_root, file_id),
        "current_toml": get_synth_toml(osii_root, file_id),
        "syntheses": list_syntheses(osii_root, file_id),
    }