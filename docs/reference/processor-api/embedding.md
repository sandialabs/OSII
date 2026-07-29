# Embedding API

`POST /v1/embed` maps identified strings to vectors. It does not decide how
documents are chunked; the core owns chunk identity and index persistence.

## Request

```json
{
  "api_version": "v1",
  "request_id": "embed-12",
  "inputs": [
    {"id": "chunk-1", "text": "first chunk", "metadata": {"file_id": "a"}},
    {"id": "chunk-2", "text": "second chunk", "metadata": {"file_id": "b"}}
  ],
  "config": {"normalize": true}
}
```

## Response

```json
{
  "api_version": "v1",
  "request_id": "embed-12",
  "processor": {"...descriptor": "..."},
  "model": "local-domain-embedding-v1",
  "vectors": [
    {"id": "chunk-1", "vector": [0.12, -0.03], "dimensions": 2},
    {"id": "chunk-2", "vector": [0.08, 0.11], "dimensions": 2}
  ],
  "normalized": true,
  "metadata": {}
}
```

Every input must produce exactly one vector with the same ID. All vectors in a
response must use one model and dimension. The core rejects mismatches before
updating an index.

The bundled Jina service remains the local production option. The SDK example
uses a deterministic toy vector only to explain the interface.

See `examples/embedder.py`.
