from fastapi import APIRouter, Query, Request

from osii.domain.services.search import dashboard_search, retrieve_dashboard
from osii.domain.storage.retrieval import RetrievalRequest
from osii.domain.read.contracts import ReadScope
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
        kind = scope.get("scope_type") or scope.get("type") or "root"
        identity = scope.get({"object": "file_id", "folder": "folder_id", "collection": "collection_id"}.get(kind), "")
        found = retrieve_dashboard(osii_root, RetrievalRequest(query, ReadScope(kind, identity),
            mode, top_k, group_by=group_by), search=dashboard_search)
        retrieval_mode_used, results = found.actual_mode, found.legacy_rows()
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
