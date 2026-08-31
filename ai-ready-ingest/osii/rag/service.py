"""Core RAG orchestration, independent of the HTTP transport."""

from pathlib import Path

from osii.domain.artifacts.text_spans import get_text_context_by_span
from osii.domain.services.search import dashboard_search
from osii.rag.config import get_chat_settings
from osii.rag.generation import run_chat_completion
from osii.rag.models import ChatRequest, ChatResponse, CitationModel


class RagRetrievalError(RuntimeError):
    """Raised when grounded evidence cannot be retrieved."""


class RagGenerationError(RuntimeError):
    """Raised when every configured answer-generation method fails."""


def _evidence(osii_root: Path, results: list[dict]) -> tuple[list[dict], list[CitationModel]]:
    evidence: list[dict] = []
    citations: list[CitationModel] = []
    for item in results:
        snippet = item.get("snippet")
        if (
            not snippet
            and item.get("file_id")
            and item.get("char_start") is not None
            and item.get("char_end") is not None
        ):
            context = get_text_context_by_span(
                osii_root,
                str(item["file_id"]),
                char_start=int(item["char_start"]),
                char_end=int(item["char_end"]),
                context_chars=300,
            )
            snippet = context.get("match_text") if context else None
        row = {
            "file_id": item.get("file_id"),
            "filename": item.get("filename"),
            "source_relpath": item.get("source_relpath"),
            "snippet": snippet,
            "chunk_id": item.get("chunk_id"),
            "segment_id": item.get("segment_id"),
            "page": item.get("page"),
            "char_start": item.get("char_start"),
            "char_end": item.get("char_end"),
            "source_origin": item.get("source_origin"),
        }
        evidence.append(row)
        citations.append(CitationModel(**row))
    return evidence, citations


def answer_question(osii_root: Path, request: ChatRequest) -> ChatResponse:
    settings = get_chat_settings(osii_root)
    scope = request.scope.model_dump()
    try:
        retrieval_mode, results = dashboard_search(
            osii_root,
            query=request.query,
            mode=settings.preferred_search_mode,
            top_k=request.top_k or settings.chat_max_results,
            scope=scope,
        )
    except (RuntimeError, ValueError) as exc:
        # A new OSII installation has no chunk manifest until its first run.
        if "No valid chunk rows found in chunk manifest" in str(exc):
            retrieval_mode, results = "empty", []
        else:
            raise RagRetrievalError(str(exc)) from exc
    except Exception as exc:
        raise RagRetrievalError(str(exc)) from exc

    evidence, citations = _evidence(osii_root, results)
    failures: list[str] = []
    for provider in settings.chat_provider_chain:
        model = settings.chat_model
        if provider == "ollama":
            model = settings.ollama_chat_model
        elif provider in {"openai", "shirty"}:
            model = settings.openai_chat_model or model
        try:
            answer = run_chat_completion(
                provider=provider,
                settings=settings,
                model=model,
                query=request.query,
                scope={**scope, "retrieval_mode": retrieval_mode},
                history=[turn.model_dump() for turn in request.history],
                evidence=evidence,
            )
            return ChatResponse(
                answer=answer,
                citations=citations,
                provider=provider,
                fallback_used=provider != settings.chat_provider_chain[0],
                retrieval_mode=retrieval_mode,
            )
        except Exception as exc:
            failures.append(f"{provider}: {exc}")
    raise RagGenerationError("; ".join(failures))
