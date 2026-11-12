"""Presentation-neutral readiness for the shared workbench home."""

from __future__ import annotations


def home_state(
    *,
    documents: int,
    text_documents: int,
    indexed_documents: int,
    chat_configured: bool,
    index_ready: bool,
    setup_dismissed: bool,
    can_setup: bool = True,
) -> dict:
    def state(enabled: bool, ready: str, blocked: str) -> dict:
        return {"enabled": bool(enabled), "reason": ready if enabled else blocked}

    has_documents = documents > 0
    has_text = text_documents > 0
    ai_ready = has_text and chat_configured
    ai_reason = (
        "No document text yet"
        if not has_text
        else (
            "Configure an AI model in Setup"
            if can_setup
            else "Ask your administrator to configure an AI model"
        )
    )
    return {
        "setup": {"visible": can_setup and not setup_dismissed},
        "documents": documents,
        "text_documents": text_documents,
        "indexed_documents": indexed_documents,
        "tools": {
            "browse": state(
                has_documents, f"{documents:,} documents available", "No documents yet"
            ),
            "search": state(
                has_text,
                "Lexical search ready; embeddings are optional",
                "No document text yet",
            ),
            "chat": state(
                ai_ready,
                "AI model configured · connection checked when used",
                ai_reason,
            ),
            "research": state(
                ai_ready,
                "AI model configured · connection checked when used",
                ai_reason,
            ),
            "overview": state(
                has_documents, "Library metadata available", "No documents yet"
            ),
            "topics": state(
                index_ready and indexed_documents > 0,
                f"{indexed_documents:,} of {documents:,} documents ready",
                "No compatible embeddings ready",
            ),
        },
    }
