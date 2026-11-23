# EmbeddingGemma 2

Optional Processor API embedder for local semantic search. It starts a CPU-only
llama.cpp server when first used, sends bounded text requests over an
authenticated loopback connection, and returns normalized 256-dimensional
vectors. Core owns the index and originals. The processor accepts documents by
default and applies the search-query prompt when an input has
`metadata.purpose = "query"`. Its descriptor opts in through the
`x-osii-embedding-input-purpose` annotation in the existing configuration
schema.

For source development, obtain a [llama.cpp CPU build](https://github.com/ggml-org/llama.cpp/releases/tag/b12651)
and compatible [text-only EmbeddingGemma 2 GGUF weights](https://huggingface.co/unsloth/embeddinggemma-2-GGUF).
Use absolute paths and keep the model and executable outside Git. The module
is disabled by default. To enable it in OSII Dev, set these values in the root
`.env` and restart the source launcher.

```dotenv
OSII_ENABLE_EMBEDDINGGEMMA=true
OSII_EMBEDDINGGEMMA_ENGINE=/absolute/path/to/llama-server
OSII_EMBEDDINGGEMMA_WEIGHTS=/absolute/path/to/embeddinggemma-2-UD-Q4_K_XL.gguf
OSII_DEFAULT_EMBEDDER=local.embeddinggemma
EMBEDDING_MODEL=embeddinggemma-2-text-256-v1
```

On Windows, point to `llama-server.exe`. The startup default applies when the
profile has no saved embedding connection. To use it in an existing development
profile, remove the `embedding` entry from the `[defaults]` table in
`models.toml`, then build an index with the newly selected model. Keep the
weights fixed for a given index. The response records the weight digest.

For a separate service, set the two asset paths and run
`uv run python -m uvicorn osii_embeddinggemma.main:app --host 127.0.0.1 --port 8114`
from this module's directory. This service accepts locally trusted Processor API
clients. Keep it on loopback.
