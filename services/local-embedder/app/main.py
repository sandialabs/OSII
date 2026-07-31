from __future__ import annotations

import hashlib
import math
import os
import re
from pathlib import Path

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


HASH_DIMENSIONS = 384
HASH_MODEL = "osii-local-hashing-v1"
TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def hashing_vector(text: str) -> list[float]:
    tokens = TOKEN_RE.findall(text.lower())
    features = [*tokens, *(f"{left}::{right}" for left, right in zip(tokens, tokens[1:]))]
    vector = [0.0] * HASH_DIMENSIONS
    for feature in features:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big") % HASH_DIMENSIONS
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


class LocalHashingEmbedder(Embedder):
    descriptor = ProcessorDescriptor(
        name="local.hashing",
        version="1.0.0",
        display_name="Local Lexical Hashing Embedder",
        description="Zero-download deterministic token and bigram hashing vectors.",
        kind=ProcessorKind.EMBEDDER,
        capabilities=Capability(output_kinds=["embedding_vector"]),
        config_schema={"type": "object", "properties": {}, "additionalProperties": False},
    )

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        return EmbeddingResponse(
            request_id=request.request_id,
            processor=self.descriptor,
            model=HASH_MODEL,
            vectors=[EmbeddingVector(id=item.id, vector=hashing_vector(item.text), dimensions=HASH_DIMENSIONS) for item in request.inputs],
            normalized=True,
            metadata={"provider": "hashing", "semantic": False},
        )


class LocalModel2VecEmbedder(Embedder):
    def __init__(self) -> None:
        try:
            from model2vec import StaticModel
        except ImportError as exc:
            raise RuntimeError("Model2Vec mode requires the 'model2vec' optional dependency.") from exc
        model_path = os.getenv("OSII_MODEL2VEC_MODEL", "minishlab/potion-base-32M")
        if os.getenv("OSII_OFFLINE", "").lower() in {"1", "true", "yes"} and not Path(model_path).exists():
            raise RuntimeError("Offline Model2Vec mode requires OSII_MODEL2VEC_MODEL to point to staged model files.")
        self.model_name = model_path
        self.model = StaticModel.from_pretrained(model_path)
        self.descriptor = ProcessorDescriptor(
            name="local.model2vec",
            version="1.0.0",
            display_name="Local Model2Vec Embedder",
            description="Optional compact semantic embeddings from a staged Model2Vec model.",
            kind=ProcessorKind.EMBEDDER,
            capabilities=Capability(output_kinds=["embedding_vector"]),
        )

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        rows = self.model.encode([item.text for item in request.inputs])
        vectors = []
        for item, row in zip(request.inputs, rows):
            values = [float(value) for value in row]
            norm = math.sqrt(sum(value * value for value in values)) or 1.0
            normalized = [value / norm for value in values]
            vectors.append(EmbeddingVector(id=item.id, vector=normalized, dimensions=len(normalized)))
        return EmbeddingResponse(
            request_id=request.request_id,
            processor=self.descriptor,
            model=self.model_name,
            vectors=vectors,
            normalized=True,
            metadata={"provider": "model2vec", "semantic": True},
        )


provider = os.getenv("OSII_LOCAL_EMBEDDING_PROVIDER", "hashing").strip().lower()
processor = LocalModel2VecEmbedder() if provider == "model2vec" else LocalHashingEmbedder()
app = create_processor_app(processor)

