# OSII architecture

## Design rule

The OSII core owns canonical persistence. Processors are replaceable compute
services and do not mount or mutate `.osii`.

The dashboard, REST API, and MCP interface are peers over the same logical
resources. A standard artifact written by an enricher must be usable by both a
person in the dashboard and an agent without processor-specific integration.

```text
Dashboard / MCP
      |
      v
OSII API + grounded chat  ----> job worker (migration target)
          |
          +----> extractor services
          +----> synthesizer services
          +----> embedder services
          +----> enricher services
          |
          v
  canonical .osii store
```

## Processor API v1

Every external processor implements:

- `GET /health`
- `GET /v1/descriptor`
- one kind-specific operation: `/v1/extract`, `/v1/synthesize`, `/v1/embed`, or
  `/v1/enrich`

The descriptor declares one processor kind, supported media/scope types,
outputs, and a JSON configuration schema. A process request contains either one
document or one scope snapshot. A response contains text segments and/or typed
artifacts.

Requests are self-contained. Source bytes are base64 encoded when required.
Text-oriented processors receive preferred text and provenance. This makes a
processor independently testable and prevents third-party code from corrupting
the store.

The protocol initially favors simple JSON over throughput. Large-artifact
transport (signed object URLs or multipart streaming) can be added compatibly
after real workload measurements.

## Migration

Current extractors, synthesizers, and enrichers remain in-process while they are
moved one at a time:

1. wrap the implementation with `osii-processor-sdk`;
2. add golden contract tests;
3. register its service URL;
4. compare its output with the local implementation;
5. remove the local implementation after its routes/configuration use the
   remote processor.

Remote enrichers are supported in the first migration slice. Remote extractors,
synthesizers, and embedders now have explicit wire contracts but still need
core-side commit adapters.

## RAG ownership

OSII Core owns the complete grounded-answer pipeline under `osii/rag`:

1. validate the requested scope;
2. retrieve lexical, semantic, or hybrid evidence from the canonical corpus;
3. preserve source spans and citations;
4. invoke the selected model method or the local extractive fallback; and
5. return one typed answer with the retrieval mode and actual provider used.

The FastAPI `/api/chat` route is a thin transport adapter over this pipeline.
The dashboard calls that route; there is no separate RAG service or RAG image.
Future query planning and iterative retrieval belong in this Core pipeline.
Model-heavy reranking may be supplied by a stateless processor, but Core keeps
ownership of the sequence, scope, evidence, and final citations.

## Repository boundaries

- `packages/osii-processor-sdk`: public contracts and service/client helpers
- `services`: independently deployable processors
- `ai-ready-ingest`: core domain, persistence, API, RAG orchestration, grounded
  chat, and transitional local processors
- `osii-dashboard`: browser application
- `ai-ready-mcp`: agent-facing adapter
- `osii-model-tool-chest` (separate repository): swappable, recommended model
  and OCR implementations such as the OpenCV/Tesseract region extractor
- `ai-ready-tool-shelf`: genuinely one-off utilities that are not recommended
  OSII deployment components

## Trust boundary

Processor services should be treated as untrusted compute:

- no OSII data-volume mount;
- only requested documents leave the core;
- configuration is validated against the descriptor schema;
- responses are size-limited and schema-validated;
- the core assigns canonical paths and commits outputs;
- network authentication is required outside a private local network.
