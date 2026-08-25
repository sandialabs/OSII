# Model providers and bridges

OSII deliberately distinguishes model providers from Processor API services.

- A **model provider** is Ollama, Shirty, or a generic OpenAI-compatible HTTP
  server. A thin bridge adapts its API.
- A **Processor service** is a domain extension implementing OSII Processor API
  v1 directly: extractor, synthesizer, embedder, or enricher.
- A **guaranteed local capability** needs neither of those.

Do not register Shirty or Ollama as a custom Processor endpoint in Tools.

## Ollama

Run Ollama separately; normal `make dev` uses it when reachable. The bridge
calls native `/api/embed` for normalized batch embeddings and `/api/chat` for
generation. The Tools pane calls `/api/tags` to show installed models beside
the endpoint configuration.

First-run selections are Ollama's
[`all-minilm`](https://ollama.com/library/all-minilm) for embeddings and Meta
[`llama3.2:1b`](https://ollama.com/library/llama3.2) for chat and synthesis.
Both are US-origin defaults sized for an ordinary workstation. If either is
absent, Tools can explicitly call Ollama's documented
[`/api/pull`](https://docs.ollama.com/api/pull) endpoint and show download
progress. The default download allowlist contains only those two names and can be extended through
`OSII_OLLAMA_ALLOWED_MODELS`. OSII installs no Ollama Python package and
bundles no server or weights.

Configure non-secret fields in **Tools & services → AI models**: provider ID, base
URL, enabled state, priority, and exact embedding/synthesis/chat model names.
Missing installed models still include copy-paste `ollama pull <model>`
commands for environments where browser-initiated downloads are disabled.

Saving every model provider as disabled is an explicit opt-out: OSII returns
to hashing embeddings and extractive synthesis/chat. Enabled providers are
selected by priority and capability, so a reliable OpenAI-compatible or Shirty
endpoint can replace Ollama without changing Intake or the dashboard.

## Generic OpenAI-compatible services

The bridge maps `/embeddings` and `/chat/completions` to Processor API
embedding/synthesis and the shared chat interface. Configure its `/v1` base
URL and explicit model names. Set only the *name* of the credential environment
variable in Tools, such as `OSII_MODEL_API_KEY`; set its value in the process
environment.

## Shirty

Shirty compatibility is included in OSII's existing HTTP-only provider
service; the public workspace does not install or import `shirty[client]`.
The adapter follows the documented API directly:

- `POST /extract/textract/create` for `corporate.shirty-textract`
- `POST /chat/completions` for `corporate.shirty-synthesis` and chat
- `GET /models` for connection and model discovery

Set `SHIRTY_BASE_URL`, `SHIRTY_API_KEY`, and an explicit chat/synthesis model.
The documented `OPENAI_BASE_URL` and `OPENAI_API_KEY` aliases are also
accepted. OSII stores only the configured environment-variable name.

OSII does not advertise a Shirty embedder. The published Shirty embedding
example installs a local Sentence Transformers implementation and does not
define a server-side embedding route. Use Ollama or a verified generic
OpenAI-compatible embedding endpoint instead.

`make dev-corporate` selects the bundled Shirty extraction and synthesis
adapters, Ollama embedding, and labeled fallbacks. A test-only exact HTTP
emulator lives in `services/model-provider-bridge/tests/fake_shirty_server.py`;
the service README includes deterministic, Tesseract-forwarding, commercial
OpenAI-forwarding, and live corporate contract-test commands.

Intake advertises the independent `local.native-text` and
`local.extractive-preview` services when they are running. Legacy sanity-check
synthesizers such as `firstN` remain importable for compatibility tests, but
are never advertised or appended to normal fallback chains. Model-provider
choices include the configured model in their label (for example, `Ollama
Synthesizer · llama3.2:1b`).

Tools groups guaranteed local capabilities under Extraction, Synthesis,
Embedding, and Enrichment. Each entry shows whether it is the Intake default,
ready, started automatically by `make dev`, built into core, or an optional
tool that must be started separately. The local hashing embedder remains
visible here even when an Ollama embedder is selected.

The same groups expose schema-driven processor settings. Ollama and generic
OpenAI-compatible synthesizers publish their grounded synthesis prompt,
temperature, and output-token limit. The LLM Wiki enricher publishes its wiki
prompt and input/output bounds. Saved defaults apply to Intake, file actions,
and direct enrichment jobs; an explicit request configuration overrides them.

## Secret handling

Provider JSON stores no secret values. Credentials are read only from
`SHIRTY_API_KEY`, `OSII_MODEL_API_KEY`, or the explicitly configured
environment-variable name. OSII does not write credentials into `.osii`,
browser storage, logs, or provider configuration.

## Index identity

Embedding failover differs from chat failover: OSII never mixes vector spaces.
Each semantic index records provider ID, endpoint type, model, model digest
when available, dimensions, normalization, chunking settings, and creation
time in a provider/model-specific directory. A model or dimension change
requires a new index; BM25 remains available while it is built.

The bridge exposes live docs at <http://localhost:8095/docs>. Provider-specific
Processor mounts are `/ollama/embedder`, `/ollama/synthesizer`,
`/openai/embedder`, and `/openai/synthesizer`.
