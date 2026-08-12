from __future__ import annotations

import hashlib
import math
import re

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
        description=(
            "A zero-download lexical baseline that converts tokens and adjacent word pairs "
            "into deterministic, normalized 384-dimensional vectors. It helps match shared "
            "wording, but does not understand semantic synonyms like a model embedding does."
        ),
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


app = create_processor_app(LocalHashingEmbedder())
