from __future__ import annotations

from abc import ABC, abstractmethod

from fastapi import FastAPI

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
            return processor.extract(request)
    elif isinstance(processor, Synthesizer):
        if processor.descriptor.kind != ProcessorKind.SYNTHESIZER:
            raise ValueError("synthesizer descriptor kind must be 'synthesizer'")
        @app.post("/v1/synthesize", response_model=SynthesisResponse)
        def synthesize(request: SynthesisRequest) -> SynthesisResponse:
            return processor.synthesize(request)
    elif isinstance(processor, Embedder):
        if processor.descriptor.kind != ProcessorKind.EMBEDDER:
            raise ValueError("embedder descriptor kind must be 'embedder'")
        @app.post("/v1/embed", response_model=EmbeddingResponse)
        def embed(request: EmbeddingRequest) -> EmbeddingResponse:
            return processor.embed(request)
    elif isinstance(processor, Enricher):
        if processor.descriptor.kind != ProcessorKind.ENRICHER:
            raise ValueError("enricher descriptor kind must be 'enricher'")
        @app.post("/v1/enrich", response_model=EnrichmentResponse)
        def enrich(request: EnrichmentRequest) -> EnrichmentResponse:
            return processor.enrich(request)

    return app
