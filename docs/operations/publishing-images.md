# Corporate pilot images and Quay releases

Optional OCR, dataset, and model images now have their source in the main
repository's [Toolbox](../../toolbox/README.md), with separate copy-paste build,
run, and Quay push commands. They are not added to the three-image release
command below. In particular, the current root Compose file also expects the
Tesseract image; build/publish `-tesseract` with matching prefix/tag before
running that bundle. MiniLM and Model2Vec remain explicit opt-in builds.

OSII has one user-facing product launch and three image artifacts:

| Image suffix | Runs |
|---|---|
| `-core` | API, worker, and grounded chat |
| `-dashboard` | Static dashboard and API proxy |
| `-baseline-processors` | Extractor, synthesizer, embedder, enricher, or model bridge |

The deployment starts eight containers: the core image runs API and worker;
the baseline image runs five independently addressable processor/adapter
commands; and the dashboard serves the browser experience. Image count and
container count intentionally differ. Users run one Compose command and do not
need to manage these internal process boundaries individually.

Chat is part of the core because it uses the same scoped retrieval and
provenance model as the API. It has no persistence of its own. Optional model
providers, including the bundled OpenAI-compatible HTTP adapter, remain behind the
model-provider bridge in the baseline image.

MCP, Tika, Tesseract OCR, and example processors remain optional. Ollama and
the upstream OpenAI-compatible service are separately managed endpoints; OSII publishes no
model weights or private provider packages.

## What the platform owner provides

Before a release job can push, obtain the corporate registry hostname,
organization/namespace, repository-creation policy, CI authentication method,
runner/network policy, and required scanning/signing/retention policy. Keep
registry credentials in the approved CI secret or identity mechanism, never in
this repository or `.env`.

CI validates the three release images and starts the complete packaged stack on
every change. Publishing remains an approved, version-tagged release action
until the corporate registry team supplies those details.

## Build the three release images

Use a version tag rather than relying only on `latest`:

```bash
cd /path/to/osii
make build \
  OSII_IMAGE_PREFIX=quay.io/your-organization/osii \
  OSII_IMAGE_TAG=0.1.0
```

This produces:

```text
quay.io/your-organization/osii-core:0.1.0
quay.io/your-organization/osii-dashboard:0.1.0
quay.io/your-organization/osii-baseline-processors:0.1.0
```

On Windows PowerShell:

```powershell
.\scripts\osii.ps1 build `
  -ImagePrefix quay.io/your-organization/osii `
  -ImageTag 0.1.0
```

## Push after review

Authenticate, inspect the three local tags, and push intentionally:

```bash
podman login quay.io
make push-release \
  OSII_IMAGE_PREFIX=quay.io/your-organization/osii \
  OSII_IMAGE_TAG=0.1.0
```

Windows PowerShell:

```powershell
podman login quay.io
.\scripts\osii.ps1 push-release `
  -ImagePrefix quay.io/your-organization/osii `
  -ImageTag 0.1.0
```

`push-release` refuses the default `localhost/` prefix. It does not create Quay
permissions or repositories; the authenticated account or robot token must be
authorized for all three target names.

## Run a corporate pilot

The release owner supplies an immutable version tag. Copy `.env.example` to
`.env`, set the registry prefix, image tag, and source folder, then start the
bundle:

```dotenv
OSII_IMAGE_PREFIX=quay.io/your-organization/osii
OSII_IMAGE_TAG=0.1.0
OSII_SOURCE_DIR=C:/Users/your-name/Documents/OSII-source
```

```bash
make run
```

```powershell
.\scripts\osii.ps1 run
```

Compose uses the shared core image for API and worker and the shared baseline
image for all five capability processes. `make run` pulls missing tagged images
but passes `--no-build`, so a pilot host never quietly builds from source.

When the command settles, open the dashboard at `http://localhost:5173` and
check `http://localhost:5173/health`. Chat is available at
`/api/chat` through the dashboard and automatically falls back to a grounded,
extractive answer if a configured model provider is unavailable.

For a corporate OpenAI-compatible connection, the administrator provides
`OPENAI_BASE_URL` and `OPENAI_API_KEY` through the approved deployment secret
mechanism. The bundled model-provider bridge calls the documented OpenAI-compatible HTTP
endpoints; it does not install or import proprietary OpenAI-compatible packages. Ollama
continues to provide embedding and can be an optional chat/synthesis fallback.
