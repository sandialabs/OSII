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


@app.get("/health")
async def health():
    return {"status": "ok", "service": "osii-chat"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    runtime_settings = get_settings()
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
        failures = []
        answer = ""
        used_provider = "extractive"
        for provider in runtime_settings.chat_provider_chain:
            try:
                model = runtime_settings.chat_model
                if provider == "ollama" and runtime_settings.ollama_chat_model:
                    model = runtime_settings.ollama_chat_model
                elif provider in {"openai", "openai_compatible"} and runtime_settings.openai_chat_model:
                    model = runtime_settings.openai_chat_model
                answer = run_chat_completion(
                    provider=provider,
                    ollama_base_url=runtime_settings.ollama_base_url,
                    openai_compatible_base_url=runtime_settings.openai_compatible_base_url,
                    openai_compatible_api_key=runtime_settings.openai_compatible_api_key,
                    model=model,
                    max_tokens=runtime_settings.chat_max_tokens,
                    query=request.query,
                    scope={**request.scope.model_dump(), "retrieval_mode": retrieval_mode},
                    history=[turn.model_dump() for turn in request.history],
                    evidence=evidence,
                )
                used_provider = provider
                break
            except Exception as exc:
                failures.append(f"{provider}: {exc}")
        if not answer:
            raise RuntimeError("; ".join(failures))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to generate chat response: {exc}") from exc

    return ChatResponse(
        answer=answer,
        citations=citations,
        provider=used_provider,
        fallback_used=used_provider != runtime_settings.chat_provider_chain[0],
        retrieval_mode=retrieval_mode,
    )
