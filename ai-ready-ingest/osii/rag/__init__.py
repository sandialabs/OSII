"""Grounded retrieval-augmented generation owned by OSII Core."""

from osii.rag.models import ChatRequest, ChatResponse
from osii.rag.service import RagGenerationError, RagRetrievalError, answer_question

__all__ = [
    "ChatRequest",
    "ChatResponse",
    "RagGenerationError",
    "RagRetrievalError",
    "answer_question",
]
