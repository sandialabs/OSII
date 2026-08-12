from fastapi import APIRouter, Request

from osii.domain.keywords.manual import create_keyword_set, delete_keyword_set, list_keyword_sets

router = APIRouter(prefix="/api/keyword-sets", tags=["keywords"])


@router.get("")
async def get_keyword_sets(request: Request):
    return {"keyword_sets": list_keyword_sets(request.app.state.osii_root.resolve())}


@router.post("")
async def post_keyword_set(request: Request, payload: dict):
    try:
        record = create_keyword_set(
            request.app.state.osii_root.resolve(), name=payload.get("name", ""), keywords=payload.get("keywords", [])
        )
    except ValueError as exc:
        return {"error": str(exc)}
    return {"keyword_set": record}


@router.delete("/{set_id}")
async def delete_keyword_set_route(request: Request, set_id: str):
    if not delete_keyword_set(request.app.state.osii_root.resolve(), set_id):
        return {"error": "unknown keyword set"}
    return {"ok": True}
