"""HTTP adapter for grounded chat owned by OSII Core."""

from fastapi import APIRouter, HTTPException, Request

from osii.rag import (
    ChatRequest,
    ChatResponse,
    RagGenerationError,
    RagRetrievalError,
    answer_question,
)


router = APIRouter(prefix="/api", tags=["chat"])


@router.get("/chat/health")
def chat_health() -> dict[str, str]:
    return {"status": "ok", "service": "osii-core-chat"}


@router.post("/chat", response_model=ChatResponse)
def chat(request: Request, payload: ChatRequest) -> ChatResponse:
    try:
        return answer_question(request.app.state.osii_root.resolve(), payload)
    except RagRetrievalError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to retrieve grounded evidence: {exc}",
        ) from exc
    except RagGenerationError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to generate chat response: {exc}",
        ) from exc
