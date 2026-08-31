# Commercial vLLM lifecycle testing

This profile runs OSII outside a corporate environment against a personal,
commercial endpoint that implements the OpenAI HTTP contract. The recommended
primary target is a Runpod Serverless vLLM endpoint: it exercises a real vLLM
deployment while OSII retains local, inspectable fallbacks if the endpoint is
down or intentionally removed.

The setup uses only synthetic checks until you deliberately process a document.
Do not send corporate or sensitive source material to a personal provider.

## 1. Create an isolated provider project

Create a separate Runpod account/project, billing method, and API key for this
test environment. Deploy a vLLM Serverless endpoint for a chat-capable model.
Record its endpoint ID and the exact `--served-model-name`; vLLM requires the
served name in requests, which can differ from the Hugging Face repository
name. Runpod publishes the endpoint as:

```text
https://api.runpod.ai/v2/ENDPOINT_ID/openai/v1
```

Keep the endpoint private and limit its API key to this personal test project.
Set a small maximum worker count and an idle timeout before the first test so a
failed experiment cannot leave expensive workers running.

## 2. Configure OSII without committing a credential

Copy the values from the repository-root `.env.commercial.example` file into
the ignored repository-root `.env` file. Replace `ENDPOINT_ID` and
`YOUR_SERVED_CHAT_MODEL`, then place the personal API key only in
`OSII_MODEL_API_KEY`.

The commercial profile makes the remote endpoint the preferred chat and
synthesis provider. It deliberately uses OSII's local lexical embedder by
default. That preserves a complete retrieval lifecycle even when the vLLM
deployment only serves a chat model. Configure a commercial embedding model
only when its endpoint implements `/embeddings`; do not describe lexical
vectors as semantic embeddings.

## 3. Validate the provider contract before starting OSII

The verifier sends a fixed synthetic prompt, lists models, and checks that a
chat completion has content. It prints only model IDs, response shape, token
usage keys, and response length; it never prints the API key or a response
body.

```bash
make provider-check
```

```powershell
.\scripts\osii.ps1 provider-check
```

When you have a separate embedding deployment, set both
`OSII_EMBEDDING_BASE_URL` and `OSII_EMBEDDING_MODEL`; the same check then
validates the vector response and reports only its dimension.

## 4. Run the isolated OSII lifecycle

Start the commercial profile:

```bash
make dev-commercial
```

```powershell
.\scripts\osii.ps1 dev-commercial
```

Open <http://localhost:5173>. Process a small synthetic corpus first, then
verify these stages in order:

1. **Intake:** original files remain in the configured source folder; OSII
   writes derived artifacts separately under `osii-data/.osii`.
2. **Search:** BM25/local lexical retrieval works independently of the remote
   model.
3. **Synthesis and chat:** OSII records the selected provider and model with
   the derived result and falls back to cited extractive output if the endpoint
   is unavailable.
4. **Failure behavior:** temporarily revoke the personal test key or stop the
   endpoint. Confirm that OSII reports the failed remote capability without
   losing canonical extractions, indexes, or source provenance.
5. **Teardown:** delete the test documents through OSII's confirmation flow,
   stop or delete the Runpod endpoint, revoke its API key, and remove the key
   from `.env` or the secret manager.

For container parity, put the same non-secret variables and key in `.env`, then
run `make containers-dev`. The Compose services receive the generic
OpenAI-compatible endpoint variables; credentials remain outside the image and
OSII store.

## What this validates

This is an integration test of OSII's OpenAI-compatible adapter and its
grounded lifecycle, not proof that a managed endpoint behaves identically to
every local vLLM configuration. Record the Runpod endpoint image/runtime,
served model name, vLLM version, worker limits, and test date with each result
that you compare over time.
