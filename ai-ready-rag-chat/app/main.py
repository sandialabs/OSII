from fastapi import FastAPI, HTTPException

from app.config import get_settings
from app.models import ChatRequest, ChatResponse, CitationModel
from app.osii_client import OsiiClient
from app.rag import run_chat_completion
from app.retrieval import retrieve_with_fallback

settings = get_settings()
osii_client = OsiiClient(settings.osii_backend_base_url)

app = FastAPI(title="AI Ready Chat")


@app.get("/")
async def root():
    return {"message": "AI Ready Chat"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        retrieval_mode, search_result = retrieve_with_fallback(
            osii_client=osii_client,
            query=request.query,
            top_k=request.top_k or settings.chat_max_results,
            scope=request.scope.model_dump(),
            preferred_mode=settings.preferred_search_mode,
            fallback_mode=settings.fallback_search_mode,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to retrieve from OSII backend: {exc}") from exc

    results = search_result.get("results", [])

    evidence = []
    citations = []

    for item in results:
        snippet = item.get("snippet")

        if not snippet and item.get("file_id") and item.get("char_start") is not None and item.get("char_end") is not None:
            try:
                ctx = osii_client.get_span_context(
                    item["file_id"],
                    int(item["char_start"]),
                    int(item["char_end"]),
                )
                snippet = ctx.get("match_text")
            except Exception:
                pass

        evidence_item = {
            "file_id": item.get("file_id"),
            "filename": item.get("filename"),
            "source_relpath": item.get("source_relpath"),
            "snippet": snippet,
            "chunk_id": item.get("chunk_id"),
            "char_start": item.get("char_start"),
            "char_end": item.get("char_end"),
            "source_origin": item.get("source_origin"),
        }
        evidence.append(evidence_item)
        citations.append(CitationModel(**evidence_item))

    try:
        answer = run_chat_completion(
            provider=settings.chat_provider,
            ollama_base_url=settings.ollama_base_url,
            model=settings.chat_model,
            max_tokens=settings.chat_max_tokens,
            query=request.query,
            scope={
                **request.scope.model_dump(),
                "retrieval_mode": retrieval_mode,
            },
            history=[turn.model_dump() for turn in request.history],
            evidence=evidence,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to generate chat response: {exc}") from exc

    return ChatResponse(
        answer=answer,
        citations=citations,
    )
