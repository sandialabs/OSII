from fastapi import APIRouter, Query, Request

from osii.domain.catalog_db import (
    list_documents,
    list_artifact_records,
    page_folders,
    rebuild_catalog,
    verify_catalog,
)
from osii.domain.read.browse import BrowseSort, browse_catalog


router = APIRouter(prefix="/api/catalog", tags=["catalog"])
browse_router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@browse_router.get("/browse")
def browse(
    request: Request,
    path: str = Query("", max_length=4096),
    query: str = Query("", max_length=256),
    sort: BrowseSort = "name-asc",
    limit: int = Query(48, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return {
        **browse_catalog(
            request.app.state.osii_root, path=path, query=query, sort=sort, limit=limit, offset=offset,
            postgres=getattr(request.app.state, "postgres_library", None),
        ),
        "source_name": request.app.state.shared_volume_root.name,
    }


@router.get("/status")
def catalog_status(request: Request):
    return verify_catalog(request.app.state.osii_root.resolve())


@router.post("/rebuild")
def rebuild(request: Request):
    return rebuild_catalog(request.app.state.osii_root.resolve())


@router.get("/files")
def files(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    cursor: str | None = None,
    status: str | None = None,
    suffix: str | None = None,
    path: str | None = None,
    text: str | None = None,
):
    return list_documents(
        request.app.state.osii_root.resolve(),
        limit=limit,
        cursor=cursor,
        status=status,
        suffix=suffix,
        path=path,
        text=text,
    )


@router.get("/folders")
def folders(request: Request, limit: int = Query(100, ge=1, le=500), cursor: str | None = None, path: str | None = None, text: str | None = None):
    return page_folders(request.app.state.osii_root.resolve(), limit=limit, cursor=cursor, path=path, text=text)


@router.get("/artifacts")
def artifacts(request: Request, scope_type: str | None = None, scope_id: str | None = None, kind: str | None = None):
    items = list_artifact_records(request.app.state.osii_root.resolve(), scope_type=scope_type, scope_id=scope_id, kind=kind)
    return {"items": items, "total": len(items)}
