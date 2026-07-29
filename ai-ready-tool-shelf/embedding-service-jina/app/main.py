"""FastAPI application entry point for the embedding service."""

from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, HTTPException

from app.config import Settings, get_settings
from app.models import (
    HealthResponse,
    OpenAIEmbeddingItem,
    OpenAIEmbeddingRequest,
    OpenAIEmbeddingResponse,
    OpenAIEmbeddingUsage,
)
from app.service import EmbeddingService

settings: Settings = get_settings()
embedding_service: EmbeddingService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown.

    Parameters
    ----------
    app : FastAPI
        FastAPI application instance.

    Yields
    ------
    None
        Control back to the application runtime.
    """
    global embedding_service
    embedding_service = EmbeddingService(settings)
    yield


app = FastAPI(
    title="Jina Embedding Service",
    version="1.1.0",
    lifespan=lifespan,
)


def _normalize_inputs(value: str | List[str]) -> List[str]:
    """Normalize request input into a list of strings.

    Parameters
    ----------
    value : str | list[str]
        Input text or list of input texts.

    Returns
    -------
    list[str]
        Normalized list of texts.
    """
    if isinstance(value, str):
        return [value]
    return value


def _validate_texts(texts: List[str]) -> None:
    """Validate request input texts.

    Parameters
    ----------
    texts : list[str]
        Input texts to validate.

    Raises
    ------
    HTTPException
        Raised if validation fails.
    """
    if not texts:
        raise HTTPException(status_code=400, detail="input must not be empty")

    if len(texts) > settings.max_texts:
        raise HTTPException(
            status_code=400,
            detail=f"Too many inputs; max is {settings.max_texts}",
        )

    for index, text in enumerate(texts):
        if not isinstance(text, str):
            raise HTTPException(
                status_code=400,
                detail=f"input at index {index} must be a string",
            )
        if not text.strip():
            raise HTTPException(
                status_code=400,
                detail=f"input at index {index} is empty",
            )
        if len(text) > settings.max_chars_per_text:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"input at index {index} exceeds max chars "
                    f"{settings.max_chars_per_text}"
                ),
            )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Return service health status.

    Returns
    -------
    HealthResponse
        Current health information.
    """
    return HealthResponse(
        status="ok",
        model_loaded=embedding_service is not None,
        model=settings.model_name,
    )


@app.post("/v1/embeddings", response_model=OpenAIEmbeddingResponse)
def create_embeddings(request: OpenAIEmbeddingRequest) -> OpenAIEmbeddingResponse:
    """Create embeddings using an OpenAI-compatible request and response shape.

    Parameters
    ----------
    request : OpenAIEmbeddingRequest
        Embedding request payload.

    Returns
    -------
    OpenAIEmbeddingResponse
        OpenAI-compatible embedding response.

    Raises
    ------
    HTTPException
        Raised if the model is unavailable or input validation fails.
    """
    if embedding_service is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    if request.model is not None and request.model != settings.model_name:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Requested model '{request.model}' does not match "
                f"configured model '{settings.model_name}'"
            ),
        )

    if request.encoding_format != "float":
        raise HTTPException(
            status_code=400,
            detail="Only encoding_format='float' is supported",
        )

    texts = _normalize_inputs(request.input)
    _validate_texts(texts)

    embeddings = embedding_service.embed(
        texts=texts,
        batch_size=settings.default_batch_size,
        normalize=settings.normalize_embeddings,
    )

    data = [
        OpenAIEmbeddingItem(
            index=index,
            embedding=embedding,
        )
        for index, embedding in enumerate(embeddings)
    ]

    usage = OpenAIEmbeddingUsage(
        prompt_tokens=0,
        total_tokens=0,
    )

    return OpenAIEmbeddingResponse(
        data=data,
        model=settings.model_name,
        usage=usage,
    )