"""Standalone report composition; all evidence comes from canonical sidecars."""
from fastapi import APIRouter, HTTPException, Request

from osii.domain.read.sidecar import SidecarLibraryReader
from osii.domain.research import EvidenceChanged, ReportGenerationError, ReportRequest, ReportResponse, write_report
from osii.rag.config import get_chat_settings
from osii.rag.generation import run_messages

router = APIRouter(prefix="/api/research", tags=["research"])


@router.post("/report", response_model=ReportResponse)
def report(request: Request, payload: ReportRequest):
    root = request.app.state.osii_root.resolve()
    settings = get_chat_settings(root)
    provider = settings.chat_provider_chain[0]
    model = settings.ollama_chat_model if provider == "ollama" else settings.openai_chat_model or settings.chat_model
    def complete(messages):
        try:
            return run_messages(provider=provider, settings=settings, model=model,
                                messages=messages, max_tokens=6000)
        except Exception:
            raise ReportGenerationError("The writing model could not complete the report. Your draft has been preserved.") from None
    try:
        return write_report(SidecarLibraryReader(root), payload,
            None if provider == "extractive" else complete,
            provider=provider, model=model if provider != "extractive" else None)
    except EvidenceChanged as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ReportGenerationError as exc:
        raise HTTPException(502, str(exc)) from exc
