# Corporate pilot images and Quay releases

Optional OCR, dataset, and model images now have their source in the main
repository's `osii-toolbox/` directory, whose README has separate copy-paste build,
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

## Portable RHEL-family base images

OSII's public Dockerfiles default to Red Hat's freely redistributable UBI 9
base. They deliberately install the application interpreter separately with
`uv`, so the image always runs Python 3.12 even when the bootstrap Python in the
base image changes. The dashboard installs Node.js 22 only in its build stage
and serves the compiled files with Nginx from a fresh UBI 9 runtime stage.

Every normal image accepts the same `OSII_BASE_IMAGE` build argument. This lets
a deployment builder select an approved RHEL 9 image without maintaining a
fork of OSII's Dockerfiles. The replacement image must provide `dnf`, a
bootstrap `python3`/`pip`, and configured repositories containing Node.js and
Nginx. For example, using a placeholder internal registry:

```bash
make build \
  OSII_BASE_IMAGE=registry.example/approved/rhel9/python-latest \
  OSII_IMAGE_TAG=0.1.0
```

```powershell
.\scripts\osii.ps1 build `
  -BaseImage registry.example/approved/rhel9/python-latest `
  -ImageTag 0.1.0
```

`OSII_PYTHON_VERSION` is also a build argument and defaults to `3.12`. Change
it only as an intentional application-runtime upgrade, not to match whatever
Python happens to be in the base image.

### Keep corporate certificates but disable inherited proxies

Podman normally passes host proxy variables into builds and containers. When a
direct connection or an endpoint-specific network client should bypass those
proxies, add OSII's opt-in proxy switch:

```bash
make build \
  OSII_BASE_IMAGE=registry.example/approved/rhel9/python-latest \
  DISABLE_CONTAINER_PROXIES=true

make run DISABLE_CONTAINER_PROXIES=true
```

Windows PowerShell uses the equivalent switch:

```powershell
.\scripts\osii.ps1 build `
  -BaseImage registry.example/approved/rhel9/python-latest `
  -DisableContainerProxies

.\scripts\osii.ps1 run -DisableContainerProxies
```

The default is unchanged: omit the switch to let Podman inherit the host proxy
configuration. In direct mode, the launchers tell Podman not to inject proxies,
set uppercase and lowercase HTTP, HTTPS, FTP, and ALL proxy variables to empty,
and remove those variables from newly built images. They do **not** remove
`NO_PROXY`, certificate environment variables, certificate files, or the RHEL
trust store. Proxy addresses and credentials do not enter OSII configuration or
logs.

The local baseline makes no public package or model downloads at runtime.
Runtime routing matters when OSII calls Shirty or another OpenAI-compatible
provider, a remote processor, or host Ollama. It also keeps internal OSII
service traffic from being routed through an inherited proxy. Choose inherited
or direct mode according to the endpoints needed by that deployment.

This strict proxy-removal switch is supported for Podman. Docker builds that
start from a custom image with proxy variables baked into it cannot receive the
same guarantee without Dockerfile changes. Registry authentication, TLS, and
image pulls are still handled by the selected container engine; this switch
does not disable certificate verification or alter registry trust.

Tesseract is the one exception: public OCR builds default to Fedora because
public UBI repositories do not include the required Tesseract language RPMs.
Set `OSII_TESSERACT_BASE_IMAGE` separately when the approved internal
RHEL-family image exposes those RPMs. Apache Tika remains an upstream optional
image rather than an OSII-built image.

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
