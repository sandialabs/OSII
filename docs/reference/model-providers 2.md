# Model-provider capabilities

OSII does not depend on a specific model vendor or gateway SDK. Optional
model-backed features use standard OpenAI-compatible HTTP endpoints instead.
This keeps the local distribution usable without credentials and lets a
corporate deployment point OSII at its own gateway.

## Capability interfaces

The core separates three capabilities:

- `DocumentExtractor`: converts source files to grounded OSII text and
  artifacts. Bundled Tika and Tesseract are local implementations; a
  specialized corporate extractor is an external Processor API service.
- `EmbeddingClient`: creates vectors through `/v1/embeddings`. The normal
  Compose stack uses the bundled Jina service.
- `ChatClient`: produces model-backed chat and synthesis through
  `/v1/chat/completions`. It is optional; extractive chat and local text
  previews remain available when it is not configured.

## Local default

No model-gateway variables are required for normal OSII use. The bundled
embedding service is configured automatically by Compose. Chat defaults to
`extractive`, which returns grounded passages without a model call.

## Configure a compatible gateway

Set these values in `.env` when a deployment has a compatible `/v1` endpoint:

```dotenv
OSII_MODEL_BASE_URL=https://models.example.internal/v1
OSII_MODEL_API_KEY=replace-with-a-secret
CHAT_PROVIDER=openai
CHAT_MODEL=your-chat-model
```

`OSII_CHAT_BASE_URL` may override the general model URL for chat. Set
`OSII_EMBEDDING_BASE_URL` separately only when embeddings use a different
compatible service. OSII sends a Bearer token when the matching API-key value
is present.

## Corporate-specific extraction

Keep any nonstandard corporate extraction API in its own container/repository.
Implement the OSII Processor API extraction contract, deploy it beside OSII,
then register its HTTP endpoint through **Tools**. This leaves the
core, dashboard, MCP server, and local distribution free of proprietary SDKs.
