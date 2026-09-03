# MiniLM embedding API

The service listens on port `8085` and exposes an OpenAI-compatible embedding
surface.

## `GET /health`

Returns the configured model and whether startup completed successfully:

```json
{
  "status": "ok",
  "model_loaded": true,
  "model": "sentence-transformers/all-MiniLM-L6-v2"
}
```

## `POST /v1/embeddings`

Accepts one string or a list of strings:

```json
{
  "input": [
    "Sandia develops advanced national security technologies.",
    "Embeddings map text into vector space."
  ],
  "model": "sentence-transformers/all-MiniLM-L6-v2",
  "encoding_format": "float"
}
```

The `model` field is optional. When present, it must match the model reported by
`/health`. The `user` and `dimensions` fields are accepted for request-shape
compatibility; `user` is not stored and `dimensions` does not alter the output.

A successful response has this shape:

```json
{
  "object": "list",
  "data": [
    {
      "object": "embedding",
      "index": 0,
      "embedding": [0.123, 0.456]
    }
  ],
  "model": "sentence-transformers/all-MiniLM-L6-v2",
  "usage": {
    "prompt_tokens": 0,
    "total_tokens": 0
  }
}
```

The default MiniLM model returns 384-dimensional vectors. Embeddings are
L2-normalized unless `NORMALIZE_EMBEDDINGS=false` is set for the container.

## Validation and errors

The service returns `400` when:

- `input` is empty or exceeds `MAX_TEXTS`;
- a text is empty or exceeds `MAX_CHARS_PER_TEXT`;
- the requested model differs from the configured model; or
- `encoding_format` is not `float`.

It returns `503` if a request arrives before the model is loaded. Authentication
and token accounting are not implemented.
