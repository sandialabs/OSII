# Model provider bridge

HTTP-only adapters for Ollama and generic OpenAI-compatible services. The
service never bundles a model or stores credentials. OSII Setup may send an explicit, allowlisted pull request
directly to a separately running Ollama service. Configure models explicitly,
run it on port 8095, and use these Processor API base URLs:

- `/ollama/embedder`
- `/ollama/synthesizer`
- `/openai/embedder`
- `/openai/synthesizer`

Chat-compatible routes are exposed at `/{provider}/v1/chat/completions`.

The OpenAI-compatible adapter uses standard `GET /models`,
`POST /embeddings`, and `POST /chat/completions` routes. Credentials come from
`OPENAI_API_KEY`.

## Contract emulator

Start the exact fake HTTP surface:

```bash
uv run --package osii-model-provider-bridge --extra dev \
  uvicorn tests.fake_openai_server:app \
  --app-dir services/model-provider-bridge --port 8096
```

Then point the OpenAI-compatible profile at it:

```bash
OPENAI_BASE_URL=http://127.0.0.1:8096/api/v1 \
OPENAI_API_KEY=local-emulator-key make dev-openai
```

PowerShell users can run the same emulator command on one line, then use a
second terminal for OSII:

```powershell
uv run --package osii-model-provider-bridge --extra dev uvicorn tests.fake_openai_server:app --app-dir services/model-provider-bridge --port 8096

$env:OPENAI_BASE_URL = "http://127.0.0.1:8096/api/v1"
$env:OPENAI_API_KEY = "local-emulator-key"
.\scripts\osii.ps1 dev-openai
```

Set `OPENAI_EMULATOR_UPSTREAM_BASE_URL`,
`OPENAI_EMULATOR_UPSTREAM_API_KEY_ENV`, and
`OPENAI_EMULATOR_UPSTREAM_MODEL` to forward chat to a commercial
OpenAI-compatible provider. Without an upstream it returns deterministic
models, embeddings, and chat fixtures suitable for CI.

The same content-safe contract check runs against either endpoint:

```bash
uv run --package osii-model-provider-bridge python \
  services/model-provider-bridge/scripts/live_openai_contract.py
```

It prints only response shape and text length, never the API key or extracted
document text.
