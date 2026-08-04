"""Processor API embedder example; deploy any vector model behind this contract."""

import hashlib
import math

from osii_processor_sdk import (
    Capability,
    Embedder,
    EmbeddingRequest,
    EmbeddingResponse,
    EmbeddingVector,
    ProcessorDescriptor,
    ProcessorKind,
    create_processor_app,
)


class ToyLocalEmbedder(Embedder):
    descriptor = ProcessorDescriptor(
        name="example.toy-local",
        version="1.0.0",
        display_name="Toy Local Embedder",
        description="Deterministic interface demonstration; not semantically useful.",
        kind=ProcessorKind.EMBEDDER,
        capabilities=Capability(output_kinds=["embedding_vector"]),
    )

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        vectors = []
        for item in request.inputs:
            digest = hashlib.sha256(item.text.encode("utf-8")).digest()[:8]
            values = [(byte - 127.5) / 127.5 for byte in digest]
            norm = math.sqrt(sum(value * value for value in values)) or 1
            vector = [value / norm for value in values]
            vectors.append(EmbeddingVector(id=item.id, vector=vector, dimensions=8))
        return EmbeddingResponse(
            request_id=request.request_id,
            processor=self.descriptor,
            model="example-toy-sha256",
            vectors=vectors,
            normalized=True,
        )


app = create_processor_app(ToyLocalEmbedder())
