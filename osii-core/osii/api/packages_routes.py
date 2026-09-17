from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from osii.domain.osii_packages import MAX_ARCHIVE_BYTES, import_package


router = APIRouter(prefix="/api/packages", tags=["packages"])


@router.post("/import")
async def import_osii_package(request: Request, package: UploadFile = File(...)):
    content = await package.read(MAX_ARCHIVE_BYTES + 1)
    if len(content) > MAX_ARCHIVE_BYTES:
        raise HTTPException(status_code=413, detail="Package is larger than the 512 MB safety limit.")
    try:
        return import_package(request.app.state.osii_root.resolve(), content)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
