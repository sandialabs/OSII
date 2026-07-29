from fastapi import APIRouter, Query, Request

from osii.domain.read.catalog import (
    load_files_catalog,
    load_folders_catalog,
    resolve_relpath_to_folder_id,
    resolve_source_relpath_to_file_id,
)
from osii.domain.read.docs import (
    get_doc_meta,
    get_doc_overview,
)
from osii.domain.read.folders import get_folder_manifest
from osii.domain.read.folder_synthesis import (
    get_folder_overview_toml,
    get_folder_synthesis_text,
    get_folder_synthesis_toml,
    list_folder_syntheses,
)
from osii.domain.read.root import (
    get_root_descriptor,
    get_root_overview_toml,
    get_root_synth_text,
)
from osii.domain.read.manifest import list_manifest_records
from osii.domain.read.segments import get_segment_record, get_segment_text, list_segments
from osii.domain.read.artifacts import get_artifact_path, get_artifact_record, list_artifacts
from osii.domain.read.synthesis import (
    get_synth_text,
    get_synth_toml,
    list_syntheses,
)

router = APIRouter(prefix="/api/osii", tags=["osii-read"])


@router.get("/root")
async def root_descriptor(request: Request):
    osii_root = request.app.state.osii_root.resolve()
    data = get_root_descriptor(osii_root)
    if data is None:
        return {"error": "root.toml not found"}
    return data


@router.get("/root/overview")
async def root_overview(request: Request):
    osii_root = request.app.state.osii_root.resolve()
    data = get_root_overview_toml(osii_root)
    if data is None:
        return {"error": "root.overview.toml not found"}
    return data


@router.get("/root/synth")
async def root_synth(request: Request):
    osii_root = request.app.state.osii_root.resolve()
    text = get_root_synth_text(osii_root)
    if text is None:
        return {"error": "root.synth.txt not found"}
    return {"synth": text}


@router.get("/folders")
async def get_folders_catalog(request: Request):
    osii_root = request.app.state.osii_root.resolve()
    return {"folders": load_folders_catalog(osii_root)}


@router.get("/files")
async def get_files_catalog(request: Request):
    osii_root = request.app.state.osii_root.resolve()
    return {"files": load_files_catalog(osii_root)}


@router.get("/resolve/folder")
async def resolve_folder(request: Request, relpath: str = Query(...)):
    osii_root = request.app.state.osii_root.resolve()
    folder_id = resolve_relpath_to_folder_id(osii_root, relpath)
    if folder_id is None:
        return {"error": f"Folder relpath not found: {relpath}"}
    return {"relpath": relpath, "folder_id": folder_id}


@router.get("/resolve/file")
async def resolve_file(request: Request, source_relpath: str = Query(...)):
    osii_root = request.app.state.osii_root.resolve()
    file_id = resolve_source_relpath_to_file_id(osii_root, source_relpath)
    if file_id is None:
        return {"error": f"Source relpath not found: {source_relpath}"}
    return {"source_relpath": source_relpath, "file_id": file_id}


@router.get("/folders/{folder_id}/manifest")
async def folder_manifest(request: Request, folder_id: str):
    osii_root = request.app.state.osii_root.resolve()
    manifest = get_folder_manifest(osii_root, folder_id)
    if manifest is None:
        return {"error": f"Folder manifest not found: {folder_id}"}
    return manifest


@router.get("/folders/{folder_id}/overview")
async def folder_overview(request: Request, folder_id: str):
    osii_root = request.app.state.osii_root.resolve()
    data = get_folder_overview_toml(osii_root, folder_id)
    if data is None:
        return {"error": f"Folder overview not found: {folder_id}"}
    return data


@router.get("/folders/{folder_id}/synth")
async def folder_synth(request: Request, folder_id: str):
    osii_root = request.app.state.osii_root.resolve()
    text = get_folder_synthesis_text(osii_root, folder_id)
    if text is None:
        return {"error": f"Folder synth not found: {folder_id}"}
    return {"folder_id": folder_id, "synth": text}


@router.get("/folders/{folder_id}/synth-toml")
async def folder_synth_toml(request: Request, folder_id: str):
    osii_root = request.app.state.osii_root.resolve()
    data = get_folder_synthesis_toml(osii_root, folder_id)
    if data is None:
        return {"error": f"Folder synth TOML not found: {folder_id}"}
    return data


@router.get("/folders/{folder_id}/syntheses")
async def folder_syntheses(request: Request, folder_id: str):
    osii_root = request.app.state.osii_root.resolve()
    return {
        "folder_id": folder_id,
        "syntheses": list_folder_syntheses(osii_root, folder_id),
    }


@router.get("/docs/{file_id}/overview")
async def doc_overview(request: Request, file_id: str):
    osii_root = request.app.state.osii_root.resolve()
    return get_doc_overview(osii_root, file_id)


@router.get("/docs/{file_id}/meta")
async def doc_meta(request: Request, file_id: str):
    osii_root = request.app.state.osii_root.resolve()
    meta = get_doc_meta(osii_root, file_id)
    if meta is None:
        return {"error": f"Doc meta not found: {file_id}"}
    return meta


@router.get("/docs/{file_id}/manifest")
async def doc_manifest(request: Request, file_id: str):
    osii_root = request.app.state.osii_root.resolve()
    return {
        "file_id": file_id,
        "records": list_manifest_records(osii_root, file_id),
    }


@router.get("/docs/{file_id}/texts")
async def doc_texts(request: Request, file_id: str):
    osii_root = request.app.state.osii_root.resolve()
    return {
        "file_id": file_id,
        "texts": list_segments(osii_root, file_id),
    }


@router.get("/docs/{file_id}/texts/{seg}")
async def doc_text(request: Request, file_id: str, seg: int):
    osii_root = request.app.state.osii_root.resolve()
    record = get_segment_record(osii_root, file_id, seg)
    if record is None:
        return {"error": f"Text segment not found: file_id={file_id}, seg={seg}"}

    text = get_segment_text(osii_root, file_id, seg)
    return {
        "file_id": file_id,
        "record": record,
        "text": text,
    }


@router.get("/docs/{file_id}/images")
async def doc_images(request: Request, file_id: str):
    osii_root = request.app.state.osii_root.resolve()
    return {
        "file_id": file_id,
        "images": list_artifacts(osii_root, file_id),
    }


@router.get("/docs/{file_id}/images/{artifact_id}")
async def doc_image(request: Request, file_id: str, artifact_id: str):
    osii_root = request.app.state.osii_root.resolve()
    record = get_artifact_record(osii_root, file_id, artifact_id)
    if record is None:
        return {"error": f"Image artifact not found: file_id={file_id}, artifact_id={artifact_id}"}

    path = get_artifact_path(osii_root, file_id, artifact_id)
    return {
        "file_id": file_id,
        "record": record,
        "path": str(path) if path else None,
    }


@router.get("/docs/{file_id}/synth")
async def doc_synth(request: Request, file_id: str):
    osii_root = request.app.state.osii_root.resolve()
    text = get_synth_text(osii_root, file_id)
    if text is None:
        return {"error": f"Synth not found: {file_id}"}
    return {"file_id": file_id, "synth": text}


@router.get("/docs/{file_id}/synth-toml")
async def doc_synth_toml(request: Request, file_id: str):
    osii_root = request.app.state.osii_root.resolve()
    data = get_synth_toml(osii_root, file_id)
    if data is None:
        return {"error": f"Synth TOML not found: {file_id}"}
    return data


@router.get("/docs/{file_id}/syntheses")
async def doc_syntheses(request: Request, file_id: str):
    osii_root = request.app.state.osii_root.resolve()
    return {
        "file_id": file_id,
        "syntheses": list_syntheses(osii_root, file_id),
    }