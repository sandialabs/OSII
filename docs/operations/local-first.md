# Local and intermittently connected operation

OSII must remain useful when corporate model and package services are
unavailable. Container images and model weights should be staged while a
connection exists; normal corpus use can then stay local.

The Jina image downloads its configured embedding model during `docker compose
build`, so a successfully built image does not need Hugging Face access at
runtime. Tesseract language packs are likewise installed in its image.

| Capability | Fully local option | Connected enhancement |
|---|---|---|
| Extraction | Tika and OSII Tesseract | specialist/corporate extractors |
| Synthesis | deterministic FirstN synthesizer | configured local or corporate LLM |
| Embedding | bundled CPU Jina service | alternative embedding endpoint |
| Enrichment | statistics/keywords and custom SDK containers | LLM-backed enrichers |
| Search | lexical index | hybrid/vector with local Jina |
| Chat | extractive grounded fallback | Shirty-backed generative answer |
| UI | bundled dashboard container | same UI |
| Agent access | bundled MCP server | same MCP contract |

Start only the essential browsing system:

```bash
make dev
```

`make dev` starts both the API and its local worker. In the dashboard, open
**Processing** to add files from the shared volume or upload one-off files;
every request is written to `/data/.osii/state/jobs.sqlite3` before the worker
claims it. This preserves queued and completed status through an API restart
without requiring Redis, RabbitMQ, or network access.

The worker chooses extractors by file extension using
`ai-ready-ingest/config/extractor_routes.toml`: Textract is configured for PDF
and Word files, while Tika is the catch-all. Use **Admin → Processors** to
register compatible custom processor containers and verify their health and
contract with a small request. Registered enabled endpoints are also included
in processor discovery; secrets are intentionally never stored in the registry.

Start all bundled services:

```bash
make dev-all
```

`CHAT_PROVIDER=extractive` is the default and never calls a language model. It
returns the most relevant grounded passages with source labels. Set
`CHAT_PROVIDER=shirty` only when a configured model endpoint is available.

For local generative chat, start the `ollama` Compose profile, pull a model once
while connected (for example, `docker compose exec ollama ollama pull llama3.2`),
then set `CHAT_PROVIDER=ollama` and `CHAT_MODEL=llama3.2` in `.env`.

The current deterministic synthesis option is deliberately modest. A small
bundled local-LLM processor can later replace it behind the same synthesis API
without changing the core or dashboard.
