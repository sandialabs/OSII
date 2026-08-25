# Model provider bridge

HTTP-only adapters for Ollama, Shirty, and generic OpenAI-compatible services.
The service never bundles a model, imports the private Shirty package, or
stores credentials. OSII Tools may send an explicit, allowlisted pull request
directly to a separately running Ollama service. Configure models explicitly,
run it on port 8095, and use these Processor API base URLs:

- `/ollama/embedder`
- `/ollama/synthesizer`
- `/openai/embedder`
- `/openai/synthesizer`
- `/shirty/extractor`
- `/shirty/synthesizer`

Chat-compatible routes are exposed at `/{provider}/v1/chat/completions`.

Shirty compatibility follows the documented HTTP surface: multipart
`POST /extract/textract/create`, OpenAI-compatible `POST /chat/completions`,
and `GET /models`. Credentials come from `SHIRTY_API_KEY`, with
`OPENAI_API_KEY` accepted as an alias. No Shirty embedder is advertised because
the published examples describe a separately installed local Sentence
Transformers package, not a remote embedding endpoint.

## Outside-corporate contract emulator

Start the exact fake HTTP surface:

```bash
uv run --package osii-model-provider-bridge --extra dev \
  uvicorn tests.fake_shirty_server:app \
  --app-dir services/model-provider-bridge --port 8096
```

Then point the corporate profile at it:

```bash
SHIRTY_BASE_URL=http://127.0.0.1:8096/api/v1 \
SHIRTY_API_KEY=local-emulator-key make dev-corporate
```

PowerShell users can run the same emulator command on one line, then use a
second terminal for OSII:

```powershell
uv run --package osii-model-provider-bridge --extra dev uvicorn tests.fake_shirty_server:app --app-dir services/model-provider-bridge --port 8096

$env:SHIRTY_BASE_URL = "http://127.0.0.1:8096/api/v1"
$env:SHIRTY_API_KEY = "local-emulator-key"
.\scripts\osii.ps1 dev-corporate
```

Set `SHIRTY_EMULATOR_TESSERACT_URL=http://127.0.0.1:8080` on the fake server
to forward extraction to OSII-Tesseract. Set
`SHIRTY_EMULATOR_UPSTREAM_BASE_URL`, `SHIRTY_EMULATOR_UPSTREAM_API_KEY_ENV`,
and `SHIRTY_EMULATOR_UPSTREAM_MODEL` to forward chat to a commercial
OpenAI-compatible provider. With neither configured, it returns deterministic
contract fixtures suitable for CI.

The same content-safe contract check runs against either endpoint:

```bash
uv run --package osii-model-provider-bridge python \
  services/model-provider-bridge/scripts/live_shirty_contract.py \
  osii-demo-notebooks/demo-workspace/documents/purcell.pdf
```

It prints only response shape and text length, never the API key or extracted
document text.
