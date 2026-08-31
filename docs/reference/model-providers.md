# Model providers and bridges

OSII deliberately distinguishes model providers from Processor API services.

- A **model provider** is Ollama or an OpenAI-compatible HTTP server. A thin
  bridge adapts its API.
- A **Processor service** is a domain extension implementing OSII Processor API
  v1 directly: extractor, synthesizer, embedder, or enricher.
- A **guaranteed local capability** needs neither of those.

Do not register an OpenAI-compatible endpoint or Ollama as a custom Processor endpoint. Connect them
through **Setup → Connect AI**; the bundled bridge supplies the Processor API
boundary internally.

## Ollama

Run Ollama separately; normal `make dev` uses it when reachable. The bridge
calls native `/api/embed` for normalized batch embeddings and `/api/chat` for
generation. Setup calls `/api/tags` to show installed models beside
the endpoint configuration.

First-run selections are Ollama's
[`all-minilm`](https://ollama.com/library/all-minilm) for embeddings and Meta
[`llama3.2:1b`](https://ollama.com/library/llama3.2) for chat and synthesis.
Both are US-origin defaults sized for an ordinary workstation. If either is
absent, Setup can explicitly call Ollama's documented
[`/api/pull`](https://docs.ollama.com/api/pull) endpoint and show download
progress. The default download allowlist contains only those two names and can be extended through
`OSII_OLLAMA_ALLOWED_MODELS`. OSII installs no Ollama Python package and
bundles no server or weights.

Ollama reports some registry and model errors inside its streaming response
even when the HTTP request itself succeeded. OSII treats those updates as
failed jobs and displays the returned detail beside the affected model instead
of briefly showing progress and silently returning to the Download button.
For proxy, certificate, DNS, and other registry failures, the model card makes
clear that OSII reached the local Ollama server and that the outbound failure
occurred inside Ollama. It also provides a copyable `ollama pull <model>`
command for the full native diagnostic. Configure proxy credentials and trust
for the Ollama application or service; OSII never requests or stores them.

Configure the endpoint and exact language/embedding model names through
**Setup → Connect AI**. Installed Ollama models are selectable from the same
dialog. Language and embedding choices are independent because not every
generative model supports embeddings. OSII saves the exact installed name,
including its tag. Selecting a different embedding model does not reuse the
previous vector index; build a compatible index for that model.
Missing installed models still include copy-paste `ollama pull <model>`
commands for environments where browser-initiated downloads are disabled.

Saving every model provider as disabled is an explicit opt-out: OSII uses
BM25 without embeddings and extractive synthesis/chat. Enabled providers are
selected by priority and capability, so a reliable OpenAI-compatible
endpoint can replace Ollama without changing Intake or the dashboard.

## OpenAI-compatible services

The bridge maps `/embeddings` and `/chat/completions` to Processor API
embedding/synthesis and the shared chat interface. Configure its `/v1` base
URL and explicit model names. The adapter uses:

- `GET /models` for discovery
- `POST /embeddings` for semantic embeddings
- `POST /chat/completions` for synthesis and chat

Set `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_EMBEDDING_MODEL`,
`OPENAI_SYNTHESIS_MODEL`, and `OPENAI_CHAT_MODEL`, or enter the same values in
Setup. OSII stores only the configured environment-variable name in `.osii`; a
locally saved value lives in the repository-root `.env`.

Extraction remains local through the Python extractor, Apache Tika, Tesseract,
or a custom Processor API extractor. `make dev-openai` selects the bundled
OpenAI-compatible embedding/synthesis/chat adapters and keeps Ollama, BM25,
and extractive fallbacks. A test-only OpenAI-compatible emulator lives in
`services/model-provider-bridge/tests/fake_openai_server.py`.

Intake advertises the independent `local.native-text` and
`local.extractive-preview` services when they are running. Legacy sanity-check
synthesizers such as `firstN` remain importable for compatibility tests, but
are never advertised or appended to normal fallback chains. Model-provider
choices include the configured model in their label (for example, `Ollama
Synthesizer · llama3.2:1b`).

Setup summarizes Extraction, Synthesis, Embedding, and Enrichment in plain
language. Compatibility processors, technical identities, schemas, and
service URLs remain under **Advanced & diagnostics**. The local hashing
embedder is an advanced compatibility method; the primary no-model search
story is BM25.

The same groups expose schema-driven processor settings. Ollama and generic
OpenAI-compatible synthesizers publish their grounded synthesis prompt,
temperature, and output-token limit. The LLM Wiki enricher publishes its wiki
prompt and input/output bounds. Saved defaults apply to Intake, file actions,
and direct enrichment jobs; an explicit request configuration overrides them.

## Secret handling

Provider JSON stores no secret values. In host development, Setup may write a
credential to the repository-root `.env`, which `.gitignore` excludes. The
backend and provider bridge reread that file, so no restart is required.
Process environment values take precedence and cannot be replaced from the UI.
Managed/container deployments disable file writes. OSII never writes
credentials into `.osii`, browser storage, logs, or API responses.

## Index identity

Embedding failover differs from chat failover: OSII never mixes vector spaces.
Each semantic index records provider ID, endpoint type, model, model digest
when available, dimensions, normalization, chunking settings, and creation
time in a provider/model-specific directory. A model or dimension change
requires a new index; BM25 remains available while it is built.

The bridge exposes live docs at <http://localhost:8095/docs>. Provider-specific
Processor mounts are `/ollama/embedder`, `/ollama/synthesizer`,
`/openai/embedder`, `/openai/synthesizer`, `/openai/embedder`, and
`/openai/synthesizer`.
