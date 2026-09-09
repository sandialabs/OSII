# OSII Processor API v1

This file is bundled in the `osii-baseline-processors` image at
`/workspace/PROCESSOR_API.md`. It is the contract for independently deployable
OSII processors.

## Boundary

A processor computes a typed response from an explicit request. It must not
mount or write the OSII `.osii` store. OSII Core selects the processor,
validates provenance, and persists returned results.

## Required endpoints

Every Processor API v1 service exposes:

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness check |
| `GET /v1/descriptor` | Name, version, kind, capabilities, and JSON configuration schema |

It exposes one operation according to its kind:

| Kind | Operation |
|---|---|
| Extractor | `POST /v1/extract` |
| Synthesizer | `POST /v1/synthesize` |
| Embedder | `POST /v1/embed` |
| Enricher | `POST /v1/enrich` |

All JSON requests and responses contain `api_version: "v1"` and a
caller-generated `request_id`. A response must echo the request ID and include
the processor descriptor.

## Input shapes

Extractors receive one `document` with `filename`, `media_type`, and base64
`content_base64`. Synthesizers and enrichers receive an explicit `scope` with
its documents and extracted text. Embedders receive identified text `inputs`.
Every operation may receive non-secret `config` values validated by the
descriptor's JSON schema.

## Output rules

Extractors return grounded text segments with source origins. Synthesizers
return cited Markdown. Embedders preserve input IDs and ordering. Enrichers
return one of OSII's standard artifact formats. No processor response writes
files into OSII storage.

Use the service's interactive OpenAPI page at `/docs` for its exact request and
response schema. The source distribution includes the fuller reference under
`docs/reference/processor-api/`.
