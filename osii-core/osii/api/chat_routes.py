"""HTTP adapter for grounded chat owned by OSII Core."""

from fastapi import APIRouter, HTTPException, Request

from osii.rag import (
    ChatRequest,
    ChatResponse,
    RagGenerationError,
    RagRetrievalError,
    answer_question,
)

from osii.rag.models import CompareRequest, ComparisonResponse
from osii.rag.local_experiments import answer_experiment, compare_profiles, profile_catalog, CorpusChanged
from osii.rag.strategies import StrategyError


router = APIRouter(prefix="/api", tags=["chat"])


@router.get("/chat/health")
def chat_health() -> dict[str, str]:
    return {"status": "ok", "service": "osii-core-chat"}


@router.post("/chat", response_model=ChatResponse)
def chat(request: Request, payload: ChatRequest) -> ChatResponse:
    try:
        if payload.profile_id != "default":
            return answer_experiment(request.app.state.osii_root.resolve(), payload,
                                     reranker=getattr(request.app.state, "rag_reranker", None))
        return answer_question(request.app.state.osii_root.resolve(), payload)
    except CorpusChanged as exc:
        raise HTTPException(409, str(exc)) from exc
    except StrategyError as exc:
        raise HTTPException(422, str(exc)) from exc
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


@router.get("/chat/profiles")
def profiles(request: Request):
    return profile_catalog(request.app.state.osii_root.resolve(), getattr(request.app.state, "rag_reranker", None))


@router.post("/chat/compare", response_model=ComparisonResponse)
def compare(request: Request, payload: CompareRequest):
    try:
        return compare_profiles(request.app.state.osii_root.resolve(), payload,
                                reranker=getattr(request.app.state, "rag_reranker", None))
    except CorpusChanged as exc:
        raise HTTPException(409, str(exc)) from exc
    except StrategyError as exc:
        raise HTTPException(422, str(exc)) from exc
