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

First start normal OSII with `make dev` or `scripts\osii.ps1 dev`. Select an
Ollama or OpenAI-compatible synthesis model in **Setup**. Then use two more
terminals from this folder:

```bash
uv run --python 3.12 --extra dev python run.py readable --host 127.0.0.1
uv run --python 3.12 --extra dev python run.py concept-entity --host 127.0.0.1
```

The default downstream synthesizer is OSII's Ollama adapter at
`http://127.0.0.1:8095/ollama/synthesizer`. To use Shirty or another configured
OpenAI-compatible provider, set the processor's **Processor API synthesizer
URL** in Setup to `http://127.0.0.1:8095/openai/synthesizer`.

Register these endpoints in **Setup → Custom Processor API services**:

```text
http://127.0.0.1:8099
http://127.0.0.1:8100
```

Each service provides `/health`, `/v1/descriptor`, `/v1/enrich`, `/docs`,
`/redoc`, and `/openapi.json`.

## Containers

From the repository root:

```bash
make toolbox-build TOOL=llm-wikis
make toolbox-run TOOL=llm-wikis
```

PowerShell:

```powershell
.\scripts\osii.ps1 toolbox-build -Tool llm-wikis
.\scripts\osii.ps1 toolbox-run -Tool llm-wikis
```

The image runs as two containers because each URL describes exactly one
Processor API implementation. Override `OSII_WIKI_SYNTHESIZER_URL` when the
synthesizer is not reachable through the host bridge at the default address.

Run isolated tests without starting a model:

```bash
uv run --python 3.12 --extra dev pytest
```

The tests inject a deterministic fake synthesizer; no model download or network
connection is required.
