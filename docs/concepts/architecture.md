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

Core owns the protocol and canonical commit adapters. A processor can run as a
bundled local host, an independently deployed container, or an SME-owned
service without changing how Core validates and persists its response:

1. wrap the implementation with `osii.processor_sdk`, included with OSII;
2. add golden contract tests;
3. contract-test the descriptor and operation;
4. register its service URL; and
5. let Core commit the validated response and provenance.

## RAG ownership

OSII Core owns the complete grounded-answer pipeline under `osii/rag`:

1. validate the requested scope;
2. retrieve lexical, semantic, or hybrid evidence from the canonical corpus;
3. preserve source spans and citations;
4. invoke the selected model method or the local extractive fallback; and
5. return one typed answer with the retrieval mode and actual provider used.

The FastAPI `/api/chat` route is a thin transport adapter over this pipeline.
The dashboard calls that route; there is no separate RAG service or RAG image.
Basic reranking can be a bounded step in this Core pipeline, with a model-heavy
implementation supplied by a stateless processor. Core keeps ownership of the
scope, candidate evidence, provenance, and final citations.

Adaptive research is a different responsibility. A future `osii-research`
component may decompose a question, issue several searches, inspect folder
summaries, identify evidence gaps, and decide what to do next. It will use
Core's REST or MCP interfaces and write validated knowledge products through
Core; it will not bypass Core to browse or mutate `.osii`. This keeps the
trusted library data plane compact while allowing a richer agentic control
plane to evolve independently.

## Repository boundaries

- `osii-core`: core domain, persistence, API, worker, bounded RAG orchestration,
  and grounded chat
- `osii-core/osii/processor_sdk`: public contracts bundled with OSII and
  service/client helpers owned by Core
- `osii-core/services`: guaranteed local Processor API hosts; independently
  addressable and containerizable despite being grouped with their owner
- `osii-dashboard`: browser application
- `osii-mcp`: agent-facing adapter
- `osii-toolbox`: swappable OCR, dataset, and model
  implementations with independent dependencies and container builds; see
  [Toolbox deployment](../operations/publishing-images.md)
- `osii-demo-notebooks`: paired Python/Jupytext demonstrations for the public
  Core and Processor SDK interfaces

## Trust boundary

Processor services should be treated as untrusted compute:

- no OSII data-volume mount;
- only requested documents leave the core;
- configuration is validated against the descriptor schema;
- responses are size-limited and schema-validated;
- the core assigns canonical paths and commits outputs;
- network authentication is required outside a private local network.
