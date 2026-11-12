"""Core-owned RAG. Importing strategy contracts does not load a store or server."""
from importlib import import_module

__all__ = ["ChatRequest", "ChatResponse", "RagGenerationError", "RagRetrievalError", "answer_question"]


def __getattr__(name):
    if name in {"ChatRequest", "ChatResponse"}:
        return getattr(import_module("osii.rag.models"), name)
    if name in {"RagGenerationError", "RagRetrievalError", "answer_question"}:
        return getattr(import_module("osii.rag.service"), name)
    raise AttributeError(name)
