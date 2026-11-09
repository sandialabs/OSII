from fastapi import APIRouter, HTTPException, Request

from osii.domain.artifacts.read_enrichments import (
    get_object_enrichment_payload,
    get_scope_enrichment_payload,
    list_scope_enrichments,
    delete_scope_enrichment,
)

router = APIRouter(prefix="/api/enrichments", tags=["enrichments"])


@router.post("/list")
async def list_enrichments_route(request: Request, payload: dict):
    osii_root = request.app.state.osii_root.resolve()
    try:
        items = list_scope_enrichments(osii_root, payload)
    except ValueError as exc:
        return {"error": str(exc)}

    return {
        "scope": payload,
        "enrichments": items,
    }


@router.post("/payload")
async def get_scope_enrichment_route(request: Request, payload: dict):
    osii_root = request.app.state.osii_root.resolve()
    filename = str(payload.get("filename") or "")
    scope = payload.get("scope") or {}
    try:
        data = get_scope_enrichment_payload(osii_root, scope, filename)
    except ValueError as exc:
        return {"error": str(exc)}
    if data is None:
        return {"error": "enrichment not found"}
    return data


@router.delete("/payload")
async def delete_scope_enrichment_route(request: Request, payload: dict):
    osii_root = request.app.state.osii_root.resolve()
    filename = str(payload.get("filename") or "")
    scope = payload.get("scope") or {}
    try:
        result = delete_scope_enrichment(osii_root, scope, filename)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="enrichment not found")
    return result


@router.get("/objects/{file_id}/{filename}")
async def get_object_enrichment_route(request: Request, file_id: str, filename: str):
    osii_root = request.app.state.osii_root.resolve()
    data = get_object_enrichment_payload(osii_root, file_id, filename)
    if data is None:
        return {"error": "enrichment not found"}
    return data


@router.post("/revisions")
def product_revisions(request: Request, payload: dict):
    import hashlib
    from osii.domain.artifacts.products import product_path, read_product, product_input_state
    try:
        root, scope = request.app.state.osii_root.resolve(), payload.get("scope") or {}
        history = read_product(product_path(root, scope, str(payload.get("filename") or "")))
        if history["data"] is None:
            raise HTTPException(status_code=404, detail="Wiki not found")
        return {**history, "library_id": hashlib.sha256(str(root).encode()).hexdigest()[:20], "input_state": product_input_state(root, scope, history)}
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/revisions")
def save_product_revision(request: Request, payload: dict):
    import hashlib
    from osii.domain.artifacts.products import edit_product, activate_product
    try:
        root = request.app.state.osii_root.resolve()
        arguments = (root, payload.get("scope") or {}, str(payload.get("filename") or ""))
        expected = payload.get("expected_revision")
        if not isinstance(expected, str):
            raise ValueError("expected_revision is required")
        if payload.get("revision"):
            result = activate_product(*arguments, str(payload["revision"]), expected)
        else:
            markdown = payload.get("markdown")
            if not isinstance(markdown, str) or len(markdown) > 2_000_000:
                raise ValueError("Wiki text must contain at most 2,000,000 characters")
            result = edit_product(*arguments, markdown, expected)
        return {**result, "library_id": hashlib.sha256(str(root).encode()).hexdigest()[:20]}
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
