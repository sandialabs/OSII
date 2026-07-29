from fastapi import APIRouter, Query, Request

from osii.domain.services.search import dashboard_search
from osii.search.common import search_segments

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
async def search(request: Request, q: str = Query(...), top_k: int = Query(default=10)):
    osii_root = request.app.state.osii_root.resolve()
    results = search_segments(osii_root, q, top_k=top_k)
    return {
        "query": q,
        "top_k": top_k,
        "results": results,
    }


@router.post("/search")
async def search_post(request: Request, payload: dict):
    osii_root = request.app.state.osii_root.resolve()

    query = (payload.get("query") or "").strip()
    if not query:
        return {"error": "query is required"}

    mode = (payload.get("mode") or "semantic").strip().lower()
    top_k = int(payload.get("top_k", 10))
    scope = payload.get("scope") or {"scope_type": "root"}
    group_by = payload.get("group_by")

    try:
        retrieval_mode_used, results = dashboard_search(
            osii_root,
            query=query,
            mode=mode,
            top_k=top_k,
            scope=scope,
            group_by=group_by,
        )
    except ValueError as exc:
        return {"error": str(exc)}

    return {
        "query": query,
        "mode": mode,
        "retrieval_mode_used": retrieval_mode_used,
        "top_k": top_k,
        "scope": scope,
        "group_by": group_by,
        "results": results,
    }