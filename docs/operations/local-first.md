# Local and intermittently connected operation

OSII must remain useful when corporate model and package services are
unavailable. Container images and model weights should be staged while a
connection exists; normal corpus use can then stay local.

The deployment Jina image downloads its configured embedding model during
`podman-compose build`, so a successfully built image does not need Hugging
Face access at runtime. Bare-metal development caches the same model under
`osii-data/models/`. Tesseract language packs are installed in its image.

| Capability | Fully local option | Connected enhancement |
|---|---|---|
| Extraction | Tika and OSII Tesseract | specialist/corporate extractors |
| Synthesis | deterministic FirstN synthesizer | configured local or corporate LLM |
| Embedding | bundled CPU Jina service | alternative embedding endpoint |
| Enrichment | statistics/keywords and custom SDK containers | LLM-backed enrichers |
| Search | lexical index | hybrid/vector with local Jina |
| Chat | extractive grounded fallback | OpenAI-compatible generative answer |
| UI | bundled dashboard container | same UI |
| Agent access | bundled MCP server | same MCP contract |

For development, start the editable local system:

```bash
make dev
```

`make dev` keeps only Tika and Tesseract in Podman. The API, local worker,
extractive chat, and Vite dashboard run directly from source with reload
support. Development state is written to
`osii-data/.osii/state/jobs.sqlite3`; the worker can survive API reloads without
Redis, RabbitMQ, or network access.

Embeddings are deliberately excluded from the fast development path. Enable
the local Jina service only while testing semantic search:

```bash
make dev-embeddings
```

The PowerShell equivalent is `.\scripts\osii.ps1 dev-embeddings`.

To run only the supporting containers:

```bash
make dev-services
```

To test packaged images instead, use `make build` followed by `make run`.
`make containers-dev` explicitly rebuilds and runs the packaged core stack.

The worker chooses extractors by file extension using
`ai-ready-ingest/config/extractor_routes.toml`. The default routes use bundled
Tika for PDF and Office files, so normal processing does not need a corporate
extractor. Use **Admin → Processors** to register compatible custom
processor containers and verify their health and contract with a small request.
Registered enabled endpoints are also included in processor discovery; secrets
are intentionally never stored in the registry.

Start all bundled services as deployment-style containers:

```bash
make dev-all
```

`CHAT_PROVIDER=extractive` is the default and never calls a language model. It
returns the most relevant grounded passages with source labels. Set
`CHAT_PROVIDER=openai` only when an OpenAI-compatible model endpoint is
configured through `OSII_CHAT_BASE_URL` or `OSII_MODEL_BASE_URL`.

Corporate-only extraction belongs in a separate processor container registered
through Processor API v1. A corporate model gateway only needs to expose the
standard OpenAI-compatible HTTP protocol; OSII does not import its SDK.

For local generative chat, start the `ollama` Compose profile, pull a model once
while connected (for example, `docker compose exec ollama ollama pull llama3.2`),
then set `CHAT_PROVIDER=ollama` and `CHAT_MODEL=llama3.2` in `.env`.

The current deterministic synthesis option is deliberately modest. A small
bundled local-LLM processor can later replace it behind the same synthesis API
without changing the core or dashboard.
