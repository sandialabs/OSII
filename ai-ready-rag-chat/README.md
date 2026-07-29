# AI Ready Chat

AI Ready Chat is a thin HTTP RAG/chat service layered over the OSII backend.

It is responsible for:

- calling the OSII backend for retrieval and grounded text access
- assembling prompt context
- calling an optional OpenAI-compatible chat endpoint
- returning answer text plus citations

It is not responsible for:

- ingest
- canonical storage
- extraction
- synthesis
- enrichments
- search index construction

Those remain in the OSII backend.

`CHAT_PROVIDER=extractive` is the local default. To use any compatible model
gateway, set `CHAT_PROVIDER=openai`, `OSII_CHAT_BASE_URL` to its `/v1` URL,
and `OSII_MODEL_API_KEY` when authentication is required.

## Run locally

```powershell
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8611 --env-file .env
```

## Example request

```http
POST /api/chat
Content-Type: application/json
```

```json
{
  "query": "What does this collection say about calibration drift?",
  "scope": {
    "scope_type": "collection",
    "collection_id": "col-abc123"
  },
  "history": []
}
```
## Retrieval fallback behavior

The chat service prefers:

- `hybrid` retrieval by default

If embedding-backed retrieval is unavailable, it falls back automatically to:

- `lexical`

This allows grounded chat to continue when the lexical index is available but embeddings have not been built or are temporarily unavailable.
