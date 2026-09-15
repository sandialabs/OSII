from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, HTTPException

from .models import (
    EmbeddingRequest,
    EmbeddingResponse,
    EnrichmentRequest,
    EnrichmentResponse,
    ExtractionRequest,
    ExtractionResponse,
    ProcessorDescriptor,
    ProcessorKind,
    SynthesisRequest,
    SynthesisResponse,
)


class Extractor(ABC):
    descriptor: ProcessorDescriptor

    @abstractmethod
    def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        """Turn one source document into canonical segments and source artifacts."""


class Synthesizer(ABC):
    descriptor: ProcessorDescriptor

    @abstractmethod
    def synthesize(self, request: SynthesisRequest) -> SynthesisResponse:
        """Produce grounded Markdown over an object or aggregate scope."""


class Embedder(ABC):
    descriptor: ProcessorDescriptor

    @abstractmethod
    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Map identified text inputs to vectors in the same order."""


class Enricher(ABC):
    descriptor: ProcessorDescriptor

    @abstractmethod
    def enrich(self, request: EnrichmentRequest) -> EnrichmentResponse:
        """Produce one or more standard, derived artifacts over a scope."""


def create_processor_app(processor: Extractor | Synthesizer | Embedder | Enricher) -> FastAPI:
    app = FastAPI(
        title=processor.descriptor.display_name,
        version=processor.descriptor.version,
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/descriptor", response_model=ProcessorDescriptor)
    def descriptor() -> ProcessorDescriptor:
        return processor.descriptor

    if isinstance(processor, Extractor):
        if processor.descriptor.kind != ProcessorKind.EXTRACTOR:
            raise ValueError("extractor descriptor kind must be 'extractor'")
        @app.post("/v1/extract", response_model=ExtractionResponse)
        def extract(request: ExtractionRequest) -> ExtractionResponse:
            try:
                return processor.extract(request)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
    elif isinstance(processor, Synthesizer):
        if processor.descriptor.kind != ProcessorKind.SYNTHESIZER:
            raise ValueError("synthesizer descriptor kind must be 'synthesizer'")
        @app.post("/v1/synthesize", response_model=SynthesisResponse)
        def synthesize(request: SynthesisRequest) -> SynthesisResponse:
            try:
                return processor.synthesize(request)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
    elif isinstance(processor, Embedder):
        if processor.descriptor.kind != ProcessorKind.EMBEDDER:
            raise ValueError("embedder descriptor kind must be 'embedder'")
        @app.post("/v1/embed", response_model=EmbeddingResponse)
        def embed(request: EmbeddingRequest) -> EmbeddingResponse:
            try:
                return processor.embed(request)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
    elif isinstance(processor, Enricher):
        if processor.descriptor.kind != ProcessorKind.ENRICHER:
            raise ValueError("enricher descriptor kind must be 'enricher'")
        @app.post("/v1/enrich", response_model=EnrichmentResponse)
        def enrich(request: EnrichmentRequest) -> EnrichmentResponse:
            try:
                return processor.enrich(request)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

    return app


def create_openai_processor_app(
    *,
    descriptor: ProcessorDescriptor,
    handler: Callable[..., Any],
    model_capability: str,
) -> FastAPI:
    """Expose a handler that receives a normal ``openai.OpenAI`` client.

    Direct tests can call the same handler with their own client and actual
    model name. Under OSII, this adapter constructs that client from the
    request's short-lived Model Gateway context.
    """

    if model_capability not in {"chat", "embedding"}:
        raise ValueError("model_capability must be 'chat' or 'embedding'")
    requirement = descriptor.model_requirements.get(model_capability)
    if requirement not in {"required", "optional"}:
        raise ValueError(
            f"descriptor must declare {model_capability!r} as a model requirement"
        )

    app = FastAPI(title=descriptor.display_name, version=descriptor.version)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/descriptor", response_model=ProcessorDescriptor)
    def get_descriptor() -> ProcessorDescriptor:
        return descriptor

    def invoke(request: Any) -> Any:
        context = request.model_context
        if context is None or model_capability not in context.bindings:
            if requirement == "optional":
                return handler(request, client=None, model="")
            raise HTTPException(
                status_code=422,
                detail=f"This processor requires an OSII {model_capability} model connection.",
            )
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - packaging guard
            raise RuntimeError(
                "Install the processor with the OSII OpenAI extra to use model-backed handlers."
            ) from exc
        client = OpenAI(
            base_url=context.gateway_url.rstrip("/"),
            api_key=context.token,
        )
        try:
            return handler(
                request,
                client=client,
                model=context.bindings[model_capability],
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    if descriptor.kind == ProcessorKind.EXTRACTOR:
        @app.post("/v1/extract", response_model=ExtractionResponse)
        def extract(request: ExtractionRequest) -> ExtractionResponse:
            return invoke(request)
    elif descriptor.kind == ProcessorKind.SYNTHESIZER:
        @app.post("/v1/synthesize", response_model=SynthesisResponse)
        def synthesize(request: SynthesisRequest) -> SynthesisResponse:
            return invoke(request)
    elif descriptor.kind == ProcessorKind.EMBEDDER:
        @app.post("/v1/embed", response_model=EmbeddingResponse)
        def embed(request: EmbeddingRequest) -> EmbeddingResponse:
            return invoke(request)
    elif descriptor.kind == ProcessorKind.ENRICHER:
        @app.post("/v1/enrich", response_model=EnrichmentResponse)
        def enrich(request: EnrichmentRequest) -> EnrichmentResponse:
            return invoke(request)
    else:  # pragma: no cover - ProcessorKind prevents this branch
        raise ValueError(f"Unsupported processor kind: {descriptor.kind}")
    return app
