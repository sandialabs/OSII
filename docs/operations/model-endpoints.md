# Independent model endpoints

Core can use separate HTTP endpoints and credentials for chat, embeddings, and
optional RAG reranking. These settings are shared by OSII-local and OSII-server.
Chat and embeddings use OpenAI-compatible APIs. The reranking adapter uses the
[Cohere rerank request/response contract](https://docs.cohere.com/reference/rerank):
`POST <base URL>/rerank`, `model`, `query`, string `documents`, and `top_n`, returning
`results` containing `index` and `relevance_score`. Other reranking protocols need
their own Core RAG adapter. Reranking is not a processor module or Processor API kind.

| Capability | Base URL | Inline credential | Credential file |
| --- | --- | --- | --- |
| Chat | `OSII_CHAT_BASE_URL` | `OSII_CHAT_API_KEY` | `OSII_CHAT_API_KEY_FILE` |
| Embeddings | `OSII_EMBEDDING_BASE_URL` | `OSII_EMBEDDING_API_KEY` | `OSII_EMBEDDING_API_KEY_FILE` |
| Reranking | `OSII_RERANK_BASE_URL` | `OSII_RERANK_API_KEY` | `OSII_RERANK_API_KEY_FILE` |

Base URLs include the provider's API prefix, such as `/v1` or `/v2`, but not
`/chat/completions`, `/embeddings`, or `/rerank`. Credentials belong in environment
variables or private files, never URLs. Use HTTPS for remote services; HTTP is
supported for local/container/private-network services. `localhost` inside a
container refers to that container, not the host or your workstation.

## Credential precedence and compatibility

For each capability, a configured key file takes precedence over its inline key.
An unreadable configured file is an error; OSII does not fall back to a different
credential. Blank credentials allow an endpoint that does not require authentication.
API responses expose endpoint URLs and credential-presence flags, not key values.
Hosted **Models** lists configured selections separately from available models.
Use **Add language model**, **Add embedding model**, or **Change connection** to open
an endpoint dialog. Enter its address/key, click **Find available models** beside
the URL, choose a model by its displayed name, then **Save connection**. The catalog
lookup is read-only, uses no corpus text, and does not invoke models or save settings.
For OpenRouter this uses its read-only [model catalog](https://openrouter.ai/docs/api/api-reference/models/get-models)
and [embedding catalog](https://openrouter.ai/docs/api/api-reference/embeddings/list-embeddings-models).
OSII retains the provider's exact identifier internally; manual entry is an optional
fallback for services without a model catalog. Chat/embedding endpoint and selection
are saved together in one PostgreSQL transaction. **Test with sample text** is a
separate action and invokes only the chosen connection; provider charges may apply.
Local Setup uses the same endpoint fields, model picker, and catalog adapter when
adding or editing a connection. Its existing named-connection persistence remains
local. Hosted administrators can save a URL and write-only key per capability under Models.
These explicit server settings override deployment defaults; **Use deployment default**
removes the override. A URL change never reuses the old key unless it is entered again.
Server overrides, including their credentials, live in PostgreSQL, accessible only
to Core. Protect database backups as credentials. Deployment-managed key files
remain outside the database. Endpoint edits wait for queued/running jobs to finish.

If a chat or embedding URL is omitted, the legacy shared URL is used:
`OSII_MODEL_BASE_URL`, then `OPENAI_BASE_URL`. OSII-server retains its OpenRouter
default when neither is provided. A capability-specific key/file can override a
shared endpoint's credential. Otherwise the legacy key/file pairs are checked in
order: `OSII_MODEL_API_KEY`, then `OPENAI_API_KEY`.

**An explicit capability URL uses only that capability's credential.** It never
inherits the shared key, even if the URLs are identical. When splitting an existing
configuration, configure its keys explicitly. Reranking never inherits a shared
URL or key. Leave both rerank URL and model empty to disable it; configuring only
one is an error when constructing the adapter.

## OSII-local

Put the endpoint settings in the checkout's `.env`, then restart `make dev` (or
the equivalent PowerShell command). For example:

```dotenv
OSII_CHAT_BASE_URL=https://chat.example.org/v1
OSII_CHAT_API_KEY_FILE=/absolute/private/path/chat-key
OSII_CHAT_MODEL=exact-chat-model-id
OSII_EMBEDDING_BASE_URL=https://embedding.example.org/v1
OSII_EMBEDDING_API_KEY_FILE=/absolute/private/path/embedding-key
OSII_EMBEDDING_MODEL=exact-embedding-model-id
OSII_RERANK_BASE_URL=https://rerank.example.org/v2
OSII_RERANK_API_KEY_FILE=/absolute/private/path/rerank-key
OSII_RERANK_MODEL=exact-reranker-model-id
```

Chat and embedding settings seed **new** `models.toml` profiles, including separate
credential references. Existing profiles remain authoritative: edit their
connections and defaults in Setup or `models.toml`; do not delete your profile to
change an endpoint. Set `api_key_env` to the corresponding capability key name
(for example `OSII_EMBEDDING_API_KEY`, without `_FILE`). The model bridge reads
the associated secret file. It does not substitute a shared key if a selected
connection's named credential is missing. New chat connections also provide
synthesis; processor modules continue to use their explicitly bound connections.

Reranking configuration creates a callable in `app.state.rag_reranker` for
opt-in Core RAG strategies. It does not change default chat or ordinary search.
There are no automatic model downloads, index rebuilds, or model invocations
when loading configuration. Changing an embedding model requires rebuilding
compatible vectors; matching dimensions alone does not establish compatibility.

## OSII-server on a Droplet

Use **Models** in the hosted administrator sidebar to edit endpoints and keys
without restarting API or worker. Alternatively, edit deployment defaults in
`/etc/osii/runtime.env`. Select chat and embedding models by name in the hosted
administrator's model settings; those selections remain in PostgreSQL.
`OSII_CHAT_MODEL` and `OSII_EMBEDDING_MODEL` are local-profile seeds, not overrides
for the server's saved selections. `OSII_RERANK_MODEL` supplies the deployment
default; administrators can override it with a saved reranker connection:

```dotenv
OSII_CHAT_BASE_URL=https://chat.example.org/v1
OSII_CHAT_API_KEY_FILE=/run/osii-keys/chat-key
OSII_EMBEDDING_BASE_URL=https://embedding.example.org/v1
OSII_EMBEDDING_API_KEY_FILE=/run/osii-keys/embedding-key
OSII_RERANK_BASE_URL=https://rerank.example.org/v2
OSII_RERANK_API_KEY_FILE=/run/osii-keys/rerank-key
OSII_RERANK_MODEL=exact-reranker-model-id
```

The updated Droplet configurator creates `/etc/osii/keys` and mounts it read-only
at `/run/osii-keys` in API/worker only. Install the three key files there, owned
by root with mode `0440`; each contains only its own key. The environment file
stays mode `0600`. The original `/etc/osii/model-key` mount remains available for
legacy shared configuration. Inline capability keys also work in `runtime.env`
when additional secret mounts are not desired.

This requires images built from the updated code and, for the new directory
mount, regenerated systemd units. The configurator preserves an existing
`runtime.env` instead of resetting custom endpoint settings. Verify its origin,
database and mount paths when reprovisioning. Once the updated units are installed,
future deployment environment/key changes need only an API/worker restart after active jobs
finish:

```bash
systemctl restart osii-api osii-worker
systemctl is-active osii-api osii-worker
```

The model administration page shows configured models and their endpoint addresses;
connection dialogs indicate whether a saved credential is present. Discovery queries
each catalog independently using its own credential; manual model names remain
supported when a catalog is unavailable. Each test action invokes only its chosen
connection with synthetic text and may incur provider charges.
A configured reranker is available to strategies; it does not automatically
enable reranking in the hosted chat pipeline.

## OpenShift

The template retains `MODEL_BASE_URL` for legacy configuration and adds
`CHAT_BASE_URL`, `EMBEDDING_BASE_URL`, `RERANK_BASE_URL`, `RERANK_MODEL`, and the
three corresponding `*_API_KEY_FILE` parameters. Their defaults are empty.
Pass file paths such as `/run/osii-model/chat-key`,
`/run/osii-model/embedding-key`, and `/run/osii-model/rerank-key` and add those
keys to the existing `osii-model` Kubernetes Secret. That Secret directory is
already mounted only in Core API/worker. Preserve its legacy `key` entry while
using legacy configuration. Never put key values in the ConfigMap or template
parameters. Roll out both API and worker after changing settings or keys.

## Standalone Python strategies

The HTTP adapter implements the existing bounded RAG protocol:

```python
from osii.rag.strategies.http_reranker import create_reranker
from osii.rag.strategies.reranking import rerank_evidence
from osii.rag.strategies import RerankRequest

reranker = create_reranker()  # Reads environment; None means disabled. No HTTP yet.
# candidates must already be authorized Evidence records in the requested scope.
result = rerank_evidence(RerankRequest(query, tuple(candidates), top_k=8), reranker)
selected = result.evidence  # Original records, including spans and OCR geometry.
```

An endpoint can also be supplied explicitly as an `osii.model_endpoints.ModelEndpoint`.
The adapter has bounded HTTP timeouts, does not follow redirects or retry, validates
indices and finite scores, and does not accept replacement evidence text. Errors
propagate rather than silently switching providers. A strategy must account for
reranking calls separately from the runner's decider-call budget. See the
[RAG authoring guide](../extending/rag-strategies.md) for limits and composition.
