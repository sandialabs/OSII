from __future__ import annotations

import json
import urllib.error
import urllib.request

from .models import (
    EmbeddingRequest,
    EmbeddingResponse,
    EnrichmentRequest,
    EnrichmentResponse,
    ExtractionRequest,
    ExtractionResponse,
    ProcessorDescriptor,
    SynthesisRequest,
    SynthesisResponse,
)


class ProcessorClientError(RuntimeError):
    pass


class ProcessorClient:
    def __init__(self, base_url: str, *, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def descriptor(self) -> ProcessorDescriptor:
        return ProcessorDescriptor.model_validate(self._get("/v1/descriptor"))

    def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        return ExtractionResponse.model_validate(self._post("/v1/extract", request.model_dump_json()))

    def synthesize(self, request: SynthesisRequest) -> SynthesisResponse:
        return SynthesisResponse.model_validate(
            self._post("/v1/synthesize", request.model_dump_json())
        )

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        return EmbeddingResponse.model_validate(self._post("/v1/embed", request.model_dump_json()))

    def enrich(self, request: EnrichmentRequest) -> EnrichmentResponse:
        return EnrichmentResponse.model_validate(self._post("/v1/enrich", request.model_dump_json()))

    def _post(self, path: str, payload_json: str) -> dict:
        payload = payload_json.encode("utf-8")
        http_request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(http_request, timeout=self.timeout) as response:
                result = json.load(response)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:2000]
            raise ProcessorClientError(
                f"processor request failed: HTTP {exc.code}: {body or exc.reason}"
            ) from exc
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            raise ProcessorClientError(f"processor request failed: {exc}") from exc
        return result

    def _get(self, path: str) -> dict:
        try:
            with urllib.request.urlopen(f"{self.base_url}{path}", timeout=self.timeout) as response:
                return json.load(response)
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            raise ProcessorClientError(f"processor discovery failed: {exc}") from exc
