from fastapi import APIRouter, Request

from osii.domain.artifacts.text_spans import get_text_by_span, get_text_context_by_span

router = APIRouter(prefix="/api/text", tags=["text"])


@router.get("/objects/{file_id}/span")
async def get_object_text_span(
    request: Request,
    file_id: str,
    char_start: int,
    char_end: int,
):
    osii_root = request.app.state.osii_root.resolve()

    text = get_text_by_span(
        osii_root,
        file_id,
        char_start=char_start,
        char_end=char_end,
    )
    if text is None:
        return {"error": "text span not found"}

    return {
        "file_id": file_id,
        "char_start": char_start,
        "char_end": char_end,
        "text": text,
    }


@router.get("/objects/{file_id}/span/context")
async def get_object_text_span_context(
    request: Request,
    file_id: str,
    char_start: int,
    char_end: int,
    context_chars: int = 200,
):
    osii_root = request.app.state.osii_root.resolve()

    result = get_text_context_by_span(
        osii_root,
        file_id,
        char_start=char_start,
        char_end=char_end,
        context_chars=context_chars,
    )
    if result is None:
        return {"error": "text span context not found"}

    return result