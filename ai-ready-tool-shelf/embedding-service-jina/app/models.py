"""Pydantic request and response models for the embedding service."""

from typing import List, Optional, Union

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response.

    Attributes
    ----------
    status : str
        Service health status.
    model_loaded : bool
        Whether the model is loaded.
    model : str
        Model identifier configured for the service.
    """

    status: str
    model_loaded: bool
    model: str


class OpenAIEmbeddingRequest(BaseModel):
    """OpenAI-compatible embedding request model.

    Attributes
    ----------
    input : str | list[str]
        Input text or list of input texts to embed.
    model : str | None
        Requested model identifier. If provided, it must match the configured model.
    encoding_format : str
        Embedding encoding format. Only ``float`` is supported.
    dimensions : int | None
        Optional requested dimensions. Not currently supported and ignored.
    user : str | None
        Optional end-user identifier for audit or tracking.
    """

    input: Union[str, List[str]] = Field(
        ...,
        description="Input text or list of texts to embed",
    )
    model: Optional[str] = Field(
        default=None,
        description="Requested model name",
    )
    encoding_format: str = Field(
        default="float",
        description="Embedding encoding format; only 'float' is supported",
    )
    dimensions: Optional[int] = Field(
        default=None,
        description="Requested embedding dimensions; currently ignored",
    )
    user: Optional[str] = Field(
        default=None,
        description="Optional user identifier",
    )


class OpenAIEmbeddingItem(BaseModel):
    """Single embedding item in an OpenAI-compatible response.

    Attributes
    ----------
    object : str
        Object type, always ``embedding``.
    index : int
        Zero-based index of the embedding result.
    embedding : list[float]
        Embedding vector.
    """

    object: str = "embedding"
    index: int
    embedding: List[float]


class OpenAIEmbeddingUsage(BaseModel):
    """Usage summary for an embedding response.

    Attributes
    ----------
    prompt_tokens : int
        Number of prompt tokens processed.
    total_tokens : int
        Total tokens processed.
    """

    prompt_tokens: int
    total_tokens: int


class OpenAIEmbeddingResponse(BaseModel):
    """OpenAI-compatible embedding response.

    Attributes
    ----------
    object : str
        Top-level object type, always ``list``.
    data : list[OpenAIEmbeddingItem]
        Embedding items.
    model : str
        Model identifier used for embedding.
    usage : OpenAIEmbeddingUsage
        Usage statistics.
    """

    object: str = "list"
    data: List[OpenAIEmbeddingItem]
    model: str
    usage: OpenAIEmbeddingUsage