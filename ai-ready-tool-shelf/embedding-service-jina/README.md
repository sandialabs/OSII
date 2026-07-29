# Jina Embedding Service

Lightweight CPU-based embedding service using `jinaai/jina-embeddings-v2-base-en`, FastAPI, and Docker.

## Features

- OpenAI-compatible `POST /v1/embeddings` endpoint
- Health endpoint
- CPU-only runtime
- Input validation for request size and text length
- Dockerized deployment
- Windows-friendly PowerShell helper scripts

## API

### Health

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8085/health"
```

### Create Embeddings

```powershell
$body = @{
    input = @(
        "Sandia develops advanced national security technologies.",
        "Embeddings map text into vector space."
    )
    model = "jinaai/jina-embeddings-v2-base-en"
    encoding_format = "float"
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8085/v1/embeddings" `
    -ContentType "application/json" `
    -Body $body
```

### Example Request Body

```json
{
  "input": [
    "Sandia develops advanced national security technologies.",
    "Embeddings map text into vector space."
  ],
  "model": "jinaai/jina-embeddings-v2-base-en",
  "encoding_format": "float"
}
```

### Example Response Body

```json
{
  "object": "list",
  "data": [
    {
      "object": "embedding",
      "index": 0,
      "embedding": [0.123, 0.456]
    },
    {
      "object": "embedding",
      "index": 1,
      "embedding": [0.789, 0.012]
    }
  ],
  "model": "jinaai/jina-embeddings-v2-base-en",
  "usage": {
    "prompt_tokens": 0,
    "total_tokens": 0
  }
}
```

## Notes

- Only `encoding_format="float"` is supported.
- If `model` is supplied, it must match the configured model name.
- `dimensions` is accepted but currently ignored.
- `prompt_tokens` and `total_tokens` are currently returned as `0`.