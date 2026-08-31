# Guaranteed local processors

`make dev` (macOS/Linux) and `.\scripts\osii.ps1 dev` (Windows PowerShell)
start four independent Processor API v1 services. They need no container,
internet connection, corporate gateway, or downloaded model.

For packaged deployment, these four services and the lightweight model-provider
bridge share one `osii-baseline-processors` image. Each container selects one
command, so the HTTP contracts and process boundaries remain independent. See
[Publish OSII images to Quay](publishing-images.md).

| Capability | Stable name | Port | Baseline behavior |
|---|---|---:|---|
| Extractor | `local.native-text` | 8092 | Text PDFs, DOCX, PPTX, XLSX, RTF, and common text/data files |
| Synthesizer | `local.extractive-preview` | 8093 | Model-free cited Markdown assembled from extracted excerpts; not OCR and does not generate new claims |
| Embedder | `local.hashing` | 8085 | Deterministic normalized 384D token/bigram hashing for shared-wording similarity; lexical, not semantic |
| Enricher | `local.stats-keywords` | 8094 | Standard table artifact with counts and keywords |

Each exposes `/health`, `/v1/descriptor`, its `/v1/...` operation, `/docs`,
`/redoc`, and `/openapi.json`. `make dev` starts all four together; packaged
deployments run the same contracts as separate containers.

The extractor reads source bytes and returns grounded segments. It cannot OCR a
scanned PDF; connect Tesseract or another OCR Processor API service for that.
The processor never writes `.osii`: only core validates and commits results.

BM25 is OSII's zero-model search baseline. Hashing adds approximate lexical
similarity and verifies the vector-index pipeline, but it is not a semantic
language model. Every index records provider, model, dimension, and
normalization metadata. Switching vector spaces requires rebuilding.

Experimental Jina and Model2Vec services live in the separate
[OSII model tool chest](https://github.com/heidikmkv/osii-model-tool-chest).
They are not part of the OSII dependency lock, images, profiles, or recommended
runtime. Review their dependency and remote-code risks independently.

## Moving a processor to its own repository

Each `services/local-*` directory is a self-contained Python package. The
component-export script supplies a standalone Dockerfile when copying one into
its own repository; the monorepo itself uses the shared baseline image. Publish
the SDK in the destination environment and replace the workspace dependency
with that published version. Configure core with its URL in `OSII_PROCESSORS`
and select it with `OSII_DEFAULT_EXTRACTOR`, `OSII_DEFAULT_SYNTHESIZER`,
`OSII_DEFAULT_EMBEDDER`, or `OSII_DEFAULT_ENRICHER`.

The HTTP contract remains Processor API v1; no OSII-core import is required by
the extracted service.

## Minimal API examples

Every request includes a caller-generated `request_id`; every response echoes
it and includes the processor descriptor and provenance-bearing outputs.

```python
import base64, requests

result = requests.post("http://127.0.0.1:8092/v1/extract", json={
    "request_id": "demo-1",
    "document": {
        "file_id": "optional-core-id",
        "filename": "notes.txt",
        "media_type": "text/plain",
        "content_base64": base64.b64encode(b"Grounded source text").decode(),
    },
}).json()
print(result["segments"])
```

Synthesis and enrichment receive text explicitly in a standard scope:

```python
scope = {
    "scope_type": "object",
    "scope_id": "file-1",
    "documents": [{"file_id": "file-1", "filename": "notes.txt", "text": "Grounded source text"}],
}
preview = requests.post("http://127.0.0.1:8093/v1/synthesize", json={"request_id": "demo-2", "scope": scope}).json()
table = requests.post("http://127.0.0.1:8094/v1/enrich", json={"request_id": "demo-3", "scope": scope}).json()
```

Embedding preserves input IDs and order:

```python
vectors = requests.post("http://127.0.0.1:8085/v1/embed", json={
    "request_id": "demo-4",
    "inputs": [{"id": "chunk-1", "text": "Grounded source text"}],
}).json()
assert vectors["model"] == "osii-local-hashing-v1"
assert vectors["vectors"][0]["dimensions"] == 384
```

For the complete schemas and interactive requests, use each service's `/docs`
page or the versioned [Processor API reference](../reference/processor-api/index.md).
