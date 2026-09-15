# Model providers and bridges

OSII deliberately distinguishes model providers from Processor API services.

- A **model provider** is Ollama or an OpenAI-compatible HTTP server. A thin
  bridge adapts its API.
- A **Processor service** is a domain extension implementing OSII Processor API
  v1 directly: extractor, synthesizer, embedder, or enricher.
- A **guaranteed local capability** needs neither of those.

Do not register an OpenAI-compatible endpoint or Ollama as a custom Processor endpoint. Connect them
through **Setup → Model connections**. Model-backed processors then use OSII's
OpenAI-compatible **Model Gateway**; provider credentials never enter their
containers.

## Where configuration lives

Model and tool configuration is workstation state, not library content. It is
kept outside `.osii` in the operating system's application-data directory:

```text
config/
├── models.yml       # connection aliases, model names, and defaults
├── tools.yml        # processor URLs/images and model bindings
└── secrets.env      # API keys; never returned by the API
```

For source development this is `~/Library/Application Support/org.osii.launcher/config`
on macOS, `%APPDATA%\org.osii.launcher\config` on Windows, and
`$XDG_CONFIG_HOME/org.osii.launcher` on Linux. Set `OSII_CONFIG_DIR` to use a
different location. The desktop launcher keeps a separate config directory per
saved library profile and mounts it into the containers.

`models.yml` names reusable connections such as `base`, `mid`, `top`, and
`minilm`. `tools.yml` binds a processor capability to one of those aliases.
Changing a binding takes effect on the next operation; the processor does not
restart. Both files are re-read when used. If an edit contains invalid YAML,
OSII keeps the last valid generation and reports the line and column in the
Setup API.

A practical `models.yml` can mix endpoints by cost or quality. Each key is a
stable connection name, not a vendor name:

```yaml
version: 1
models:
  base:
    type: openai-compatible
    base_url: https://models.example.com/v1
    api_key_env: OPENAI_BASE_API_KEY
    model: vendor/small-instruct
    capabilities: [chat, synthesis]
  mid:
    type: openai-compatible
    base_url: https://models.example.com/v1
    api_key_env: OPENAI_MID_API_KEY
    model: vendor/general-instruct
    capabilities: [chat, synthesis]
  top:
    type: openai-compatible
    base_url: https://premium-models.example.com/v1
    api_key_env: OPENAI_TOP_API_KEY
    model: vendor/high-quality-instruct
    capabilities: [chat, synthesis]
  minilm:
    type: ollama-local
    base_url: http://127.0.0.1:11434
    model: all-minilm
    capabilities: [embedding]
defaults: {chat: base, synthesis: base, embedding: minilm}
```

The corresponding `tools.yml` states whether a processor is self-contained or
which connection it may use:

```yaml
version: 1
profiles:
  development:
    tools:
      readable-llm-wiki:
        enabled: true
        processor_id: toolbox.readable-wiki
        runtime: {mode: external, endpoint: http://127.0.0.1:8099}
        model_access: {mode: gateway, bindings: {chat: top}}
      concept-entity-llm-wiki:
        enabled: true
        processor_id: toolbox.concept-entity-wiki
        runtime: {mode: external, endpoint: http://127.0.0.1:8100}
        model_access: {mode: gateway, bindings: {chat: mid}}
      tesseract-opencv:
        enabled: true
        processor_id: toolbox.tesseract-opencv
        runtime: {mode: external, endpoint: http://127.0.0.1:8081}
        model_access: {mode: none}
```

You can create and bind all of this in Workbench Setup. The YAML is also a
deliberately readable power-user interface for review, source-controlled
deployment templates, and local processor development. Never put key values in
either YAML file; Setup writes them to `secrets.env` under the declared
environment-variable names. Setup has separate **Use as default** switches for
language and embedding connections; adding a high-cost `top` connection does
not silently make every ordinary chat request use it.

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
**Setup → Model connections**. Installed Ollama models are selectable from the same
dialog. Starter cards change from **Download** to **Installed** after model
discovery; a one-click download also selects and validates the model. Language
and embedding choices are independent because not every
generative model supports embeddings. OSII saves the exact installed name,
including its tag. Selecting a different embedding model does not reuse the
previous vector index. For documents already in OSII, run **Intake → Additional
processing → Build semantic embeddings** after selecting the model.
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

After model discovery, Setup sends one short test input to the selected
embedding model and reports the returned dimensions. This distinguishes “the
name appears in `/models`” from “this endpoint can actually embed with that
model,” which is the readiness condition Intake uses. For compatible servers
that reject OpenAI's optional `encoding_format` field, the bridge retries using
only the required `model` and `input` fields.

Enter the endpoint, model, and credential in Setup. `models.yml` stores only
the environment-variable name; a locally saved value lives in `secrets.env`.
`OPENAI_API_KEY` is the conventional default name. Process environment values
take precedence over the file.

Extraction remains local through the Python extractor, Apache Tika, Tesseract,
or a custom Processor API extractor. `make dev` automatically selects the
bundled OpenAI-compatible embedding/synthesis/chat adapters when
`OPENAI_BASE_URL` is configured, and keeps Ollama, BM25, and extractive
fallbacks. A test-only OpenAI-compatible emulator lives in
`osii-core/services/model-provider-bridge/tests/fake_openai_server.py`.

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
temperature, and output-token limit. Optional wiki enrichers publish their own
prompts and bounds through Processor API descriptors. Saved defaults apply to
Intake, file actions, and direct enrichment jobs; an explicit request
configuration overrides them.

## Model Gateway for Toolbox processors

The bridge also exposes the ordinary OpenAI client surface at
`/v1/chat/completions`, `/v1/embeddings`, and `/v1/models`. Core supplies each
model-backed processor with a short-lived job token and the gateway URL. The
token is restricted to that tool, job, capability, connection alias, request
count, and expiration. Core revokes it as soon as the synchronous processor
operation returns; its short expiration remains the fallback if the gateway is
temporarily unreachable during revocation. The gateway translates an alias
such as `top` to the actual provider model and attaches the provider credential
itself.

This lets a processor use normal, directly testable code:

```python
response = client.chat.completions.create(
    model=model,
    messages=[{"role": "user", "content": "Create a grounded wiki."}],
)
```

The processor receives neither the upstream base URL nor its API key.

## Secret handling

`models.yml` stores no secret values. In host development, Setup may write a
credential to `secrets.env`. The
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
