# MiniLM Embedding Service

CPU-only embedding service using
`sentence-transformers/all-MiniLM-L6-v2`, FastAPI, and Podman. It exposes an
OpenAI-compatible `POST /v1/embeddings` endpoint and returns normalized
384-dimensional vectors by default.

The model is downloaded while the image is built and the runtime is placed in
offline mode. Starting the finished container therefore does not contact
Hugging Face or execute remote model code.

## Build and run

This is an optional, model-heavy tool, not a Core dependency. See
[Toolbox deployment and Quay publishing](../README.md#minilm-embeds-its-model-during-the-build).
Review the existing dependency pins and model provenance before release.

From this directory:

```bash
podman build --format docker -t minilm-embedding-service .
podman run --rm -p 127.0.0.1:8086:8085 minilm-embedding-service
```

PowerShell users can run:

```powershell
.\scripts\build.ps1
.\scripts\run.ps1 -HostPort 8086
```

The container includes a health check. Wait for `/health` to report the model
as loaded before sending embedding requests:

```bash
curl http://localhost:8086/health
```

## Create embeddings

```bash
curl http://localhost:8086/v1/embeddings \
  -H 'Content-Type: application/json' \
  -d '{"input":["first document","second document"],"model":"sentence-transformers/all-MiniLM-L6-v2"}'
```

PowerShell users can exercise both endpoints with:

```powershell
.\scripts\test.ps1 -BaseUrl http://localhost:8086
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `MODEL_NAME` | `sentence-transformers/all-MiniLM-L6-v2` | Baked-in model identifier |
| `PORT` | `8085` | Service port |
| `DEFAULT_BATCH_SIZE` | `16` | Inference batch size |
| `MAX_TEXTS` | `128` | Maximum texts per request |
| `MAX_CHARS_PER_TEXT` | `50000` | Input validation limit |
| `NORMALIZE_EMBEDDINGS` | `true` | L2-normalize returned vectors |

Only `encoding_format="float"` is supported. If a request includes `model`, it
must match the configured model name. Changing the model changes vector
identity and may change dimensionality, so existing indexes must be rebuilt.

## Dependency-light tests

From this folder, validate request/response models without installing PyTorch
or downloading model weights:

```sh
uv run --no-project --python 3.11 --with-requirements requirements-test.txt python -m pytest tests -q
```
