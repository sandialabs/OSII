from pathlib import Path

from osii.model_clients import create_chat_client

from osii.domain.read.root import get_root_synth_text
from osii.domain.read.folder_synthesis import get_folder_synthesis_text
from osii.domain.read.synthesis import get_synth_text
from osii.domain.scopes.collections import get_collection
from osii.domain.scopes.scopes import (
    SCOPE_COLLECTION,
    SCOPE_DOCUMENT,
    SCOPE_FOLDER,
    SCOPE_OBJECT,
    SCOPE_ROOT,
    normalize_scope_type,
)
from osii.domain.services.search import dashboard_search


MODEL = "openai/gpt-oss-120b"


def _scope_header(osii_root: Path, scope: dict) -> tuple[str, dict]:
    scope_type = normalize_scope_type(scope.get("scope_type") or scope.get("type") or SCOPE_ROOT)

    if scope_type == SCOPE_ROOT:
        root_synth = get_root_synth_text(osii_root)
        return (
            "root",
            {
                "type": SCOPE_ROOT,
                "synth": root_synth,
            },
        )

    if scope_type == SCOPE_FOLDER:
        folder_id = scope.get("folder_id")
        if not folder_id:
            raise ValueError("folder_id is required for folder scope")
        folder_synth = get_folder_synthesis_text(osii_root, folder_id)
        return (
            "folder",
            {
                "type": SCOPE_FOLDER,
                "folder_id": folder_id,
                "synth": folder_synth,
            },
        )

    if scope_type in {SCOPE_OBJECT, "document"}:
        file_id = scope.get("file_id")
        if not file_id:
            raise ValueError("file_id is required for object scope")
        doc_synth = get_synth_text(osii_root, file_id)
        return (
            "object",
            {
                "type": SCOPE_OBJECT,
                "file_id": file_id,
                "synth": doc_synth,
            },
        )

    if scope_type == SCOPE_COLLECTION:
        collection_id = scope.get("collection_id")
        if not collection_id:
            raise ValueError("collection_id is required for collection scope")
        collection = get_collection(osii_root, collection_id)
        return (
            "collection",
            {
                "type": SCOPE_COLLECTION,
                "collection_id": collection_id,
                "name": collection["name"] if collection else None,
                "description": collection["description"] if collection else None,
                "synth": None,
            },
        )

    raise ValueError(f"Unsupported scope type: {scope_type}")


def _build_system_prompt() -> str:
    return (
        "You are a careful assistant answering questions over an OSII corpus. "
        "Use the supplied scope context and retrieved evidence. "
        "Do not invent facts. If the evidence is weak, say so."
    )


def _build_user_prompt(query: str, scope_info: dict, history: list[dict], citations: list[dict]) -> str:
    hist_lines = []
    for turn in history or []:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        hist_lines.append(f"{role.upper()}: {content}")
    history_block = "\n".join(hist_lines).strip() or "(no prior history)"

    synth = scope_info.get("synth") or "(no synthesis available for this scope)"
    citation_lines = []
    for c in citations:
        citation_lines.append(
            f"- file: {c.get('source_relpath')}\n"
            f"  segment_id: {c.get('segment_id')}\n"
            f"  page: {c.get('page')}\n"
            f"  snippet: {c.get('snippet')}\n"
            f"  source_origin: {c.get('source_origin')}"
        )
    evidence_block = "\n".join(citation_lines).strip() or "(no retrieved evidence)"

    return f"""Query:
{query}

Scope info:
{scope_info}

Scope synthesis:
{synth}

Conversation history:
{history_block}

Retrieved evidence:
{evidence_block}

Instructions:
- Answer the user query concisely and faithfully.
- Prefer scope synthesis for broad understanding and retrieved evidence for grounding.
- If evidence is insufficient, say so.
- Return only the answer text.
"""


def _call_llm(query: str, scope_info: dict, history: list[dict], citations: list[dict], model: str) -> str:
    return create_chat_client().complete(
        model=model,
        messages=[
            {"role": "system", "content": _build_system_prompt()},
            {"role": "user", "content": _build_user_prompt(query, scope_info, history, citations)},
        ],
        max_tokens=700,
    )


def dashboard_chat(
    osii_root: Path,
    *,
    query: str,
    scope: dict,
    history: list[dict] | None = None,
    top_k: int = 5,
    model: str = MODEL,
) -> dict:
    if not (query or "").strip():
        raise ValueError("query is required")

    _, scope_info = _scope_header(osii_root, scope)

    _, results = dashboard_search(
        osii_root,
        query=query,
        mode="hybrid",
        top_k=top_k,
        scope=scope,
    )

    citations = []
    for r in results:
        citations.append(
            {
                "file_id": r.get("file_id"),
                "filename": r.get("filename"),
                "source_relpath": r.get("source_relpath"),
                "segment_id": r.get("segment_id"),
                "page": r.get("page"),
                "snippet": r.get("snippet"),
                "source_origin": r.get("source_origin"),
            }
        )

    answer = _call_llm(query, scope_info, history or [], citations, model=model) or "[EMPTY_MODEL_OUTPUT]"

    return {
        "answer": answer,
        "citations": citations,
    }
