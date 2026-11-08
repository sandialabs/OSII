# Guaranteed local processors

`make dev` (macOS/Linux) and `.\scripts\osii.ps1 dev` (Windows PowerShell)
start five independent Processor API v1 services. Four need no container,
internet connection, corporate gateway, or downloaded model. The fifth is
ordinary page-by-page Tesseract OCR and requires the native `tesseract`
executable on a bare-metal host. The packaged baseline image contains that
executable and its checked language data.

For packaged deployment, these five services and the lightweight model-provider
bridge share one `osii-baseline-processors` image. Each container selects one
command, so the HTTP contracts and process boundaries remain independent. See
[Publish OSII images to Quay](publishing-images.md).

| Capability | Stable name | Port | Baseline behavior |
|---|---|---:|---|
| Extractor | `local.native-text` | 8092 | Text PDFs, DOCX, PPTX, XLSX, RTF, and common text/data files |
| OCR extractor | `local.tesseract-page-ocr` | 8080 | Runs ordinary Tesseract on each complete PDF or image page; no OpenCV region detection |
| Synthesizer | `local.extractive-preview` | 8093 | Model-free cited Markdown assembled from extracted excerpts; not OCR and does not generate new claims |
| Embedder | `local.hashing` | 8085 | Deterministic normalized 384D token/bigram hashing for shared-wording similarity; lexical, not semantic |
| Enricher | `local.stats-keywords` | 8094 | Standard table artifact with counts and keywords |

Each exposes `/health`, `/v1/descriptor`, its `/v1/...` operation, `/docs`,
`/redoc`, and `/openapi.json`. `make dev` starts all five together; packaged
deployments run the same contracts as separate containers.

The native extractor reads existing source text and cannot OCR a scanned PDF.
Select `local.tesseract-page-ocr` for those files. It returns one segment per
page; the optional `toolbox.tesseract-opencv` processor adds experimental
region detection and bounding boxes. Neither processor writes `.osii`: only
Core validates and commits results.

BM25 is OSII's zero-model search baseline. Hashing adds approximate lexical
similarity and verifies the vector-index pipeline, but it is not a semantic
language model. Every index records provider, model, dimension, and
normalization metadata. Switching vector spaces requires rebuilding.

The experimental OpenCV/Tesseract region extractor and
tabular processors live in `osii-toolbox/` in
this repository. Their dependencies remain separate from Core's lockfile and
default host runtime. Use the per-tool Python source commands and register the
running Processor API endpoint in Setup. Container builds and component export
are archived on `archive/workstation-deployment-2026-11-03`.

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


Tesseract services additionally expose `/ready`. It returns HTTP 503 when the
native executable is missing; `/health` alone only confirms the HTTP process
is alive. Install the native executable and required language data before
queuing OCR. The shared PDF viewer accepts both page `regions` and a segment's
normalized `source_origin.bbox` for overlays. OSII-tesseract remains an optional
Toolbox extractor, not a model endpoint or part of RAG orchestration.
