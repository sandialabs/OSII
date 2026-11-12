# LLM wiki enrichers

This optional Toolbox package contains two different Processor API enrichers.
They are intentionally not part of OSII Core:

- **Readable LLM wiki** (`toolbox.readable-wiki`, port 8099) creates the
  traditional, narrative wiki used by the original OSII proof of concept.
- **Concept and entity LLM wiki** (`toolbox.concept-entity-wiki`, port 8100)
  adapts the work from `upstream/dev-aditya`. It asks for durable concepts and
  specific named entities, rejects records whose evidence is absent from the
  supplied text, and returns three standard artifacts: Wiki Markdown, an
  entity list, and a sortable concept table.

Both accept object, folder, collection, and root scopes. Neither reads source
folders nor writes `.osii`: Core sends bounded extracted text to `/v1/enrich`,
validates the response, and owns the canonical commit.

## Why these are enrichers

An extractor reads one source file and returns grounded text segments and
source artifacts. These wiki builders operate on text that has already been
extracted, can combine many documents, and create derived knowledge products.
They are therefore Processor API **enrichers**, even though people may
informally call them wiki extractors.

## Run from source

First start normal OSII with `make dev` or `scripts\osii.ps1 dev`. In
**Setup → Advanced & diagnostics → Local capability services**, start either
wiki service. The equivalent direct commands from the repository root are:

```bash
uv run --project osii-processor-modules/llm-wiki-enrichers python osii-processor-modules/llm-wiki-enrichers/run.py readable --host 127.0.0.1
uv run --project osii-processor-modules/llm-wiki-enrichers python osii-processor-modules/llm-wiki-enrichers/run.py concept-entity --host 127.0.0.1
```

Register these endpoints in **Setup → Register running processor**:

```text
http://127.0.0.1:8099
http://127.0.0.1:8100
```

Each service provides `/health`, `/v1/descriptor`, `/v1/enrich`, `/docs`,
`/redoc`, and `/openapi.json`.

## Deployment status

Container workflows are archived on `archive/workstation-deployment-2026-11-03`.
Use the source commands above while hosted delivery is developed.
