# OSII Toolbox: deploy and publish

Optional tools now live here, **inside the main OSII repository**. You need only
one checkout. They still run independently: moving their source here does not
install their dependencies, start them with `make dev`, or change your selected
processors. The shared Processor SDK stays in `packages/osii-processor-sdk/`.

## Pick the capability you need

| Folder / image suffix | What it does | API | Host port in this guide |
|---|---|---|---|
| [osii-tesseract](osii-tesseract/README.md) / `-tesseract` | OpenCV region detection + Tesseract OCR; text and page bounding boxes | Processor API extractor | 8080 |
| [tabular-dataset-processors](tabular-dataset-processors/README.md) / `-tabular-dataset-processors` | CSV rows as standard tables; collection tables retaining row provenance | Processor API extractor and enricher; **one image, two processes** | 8097 / 8098 |
| [minilm-embedding-service](minilm-embedding-service/README.md) / `-minilm-embedding` | CPU MiniLM semantic embeddings, 384 dimensions | OpenAI-compatible `/v1/embeddings`, **not** Processor API | 8086 |
| [model2vec-embedder](model2vec-embedder/README.md) / `-model2vec-embedder` | Experimental semantic embeddings from an explicitly staged model | Processor API embedder | 8087 |

That is **four possible images, five containers if you run every capability**.
You need not publish or run all of them. Apache Tika is an upstream image and
Ollama is a separately managed provider; neither is copied into this Toolbox.
Core and its normal model connections remain unchanged.

## Build the two starter images

Run from the **OSII repository root**, not this folder. Podman must be running
(on macOS/Windows, start its machine first if needed). Docker is also supported:
substitute `docker` for `podman` and omit the Podman-only `--format docker`.

Choose your Quay namespace and an unused release tag. Do not use the literal
`your-namespace`. These two initializations differ by shell:

macOS/Linux:

```bash
TOOLBOX_PREFIX="quay.io/your-namespace/osii"
TOOLBOX_TAG="0.1.0"
```

Windows PowerShell:

```powershell
$TOOLBOX_PREFIX = "quay.io/your-namespace/osii"
$TOOLBOX_TAG = "0.1.0"
```

All the following one-line commands work in **both shells**:

```sh
podman build --format docker --platform linux/amd64 -f toolbox/osii-tesseract/Dockerfile -t "${TOOLBOX_PREFIX}-tesseract:${TOOLBOX_TAG}" .
podman build --format docker --platform linux/amd64 -f toolbox/tabular-dataset-processors/Dockerfile -t "${TOOLBOX_PREFIX}-tabular-dataset-processors:${TOOLBOX_TAG}" .
```

These commands target typical x86-64 Windows/Linux deployment machines. An
Apple Silicon Mac needs working x86 emulation and builds may be slow; use a
Linux x86-64 builder if necessary. For an ARM-only local test, omit `--platform`
and use a different tag. A single-platform image is not a multi-architecture
release. Builds install dependencies and require package-registry access;
running these two finished images requires no model download.

## Run and check before pushing

These launch only the chosen tools, not OSII itself. Leave `make dev` or
`.\scripts\osii.ps1 dev` running in its own terminal. If port 8080 already hosts
Tesseract, reuse that service or stop it through its owner before starting another.

```sh
podman run -d --name osii-tesseract -p 127.0.0.1:8080:8080 -e ENABLE_DEMO=false "${TOOLBOX_PREFIX}-tesseract:${TOOLBOX_TAG}"
podman run -d --name osii-csv-table-extractor -p 127.0.0.1:8097:8097 "${TOOLBOX_PREFIX}-tabular-dataset-processors:${TOOLBOX_TAG}" extractor
podman run -d --name osii-collection-table-enricher -p 127.0.0.1:8098:8098 "${TOOLBOX_PREFIX}-tabular-dataset-processors:${TOOLBOX_TAG}" enricher
podman ps
podman logs --tail 50 osii-tesseract
```

Open each service's `/health`, `/v1/descriptor`, and `/docs`, for example
<http://127.0.0.1:8080/docs> and <http://127.0.0.1:8097/docs>. Health confirms
the HTTP process is up, not OCR accuracy; exercise one document in `/docs` or
Intake before publishing. Set `ENABLE_DEMO=true` when starting Tesseract if you
want its interactive region-tuning page at `/demo`.

In **Setup**, register these as custom **Processor API** endpoints, test them,
then select the extractor/routing or enrichment you want. Alternatively append
the URLs to `OSII_PROCESSORS` in the ignored root `.env` and restart OSII:

```dotenv
# Preserve any existing URLs too; this is an example, not an append operation.
OSII_PROCESSORS=http://127.0.0.1:8080,http://127.0.0.1:8097,http://127.0.0.1:8098
```

Do not mount `.osii` or your document directories into these containers. Core
sends the selected bytes/text and saves returned artifacts. Container-to-container
connections must use shared-network service names or a reachable host address,
not `127.0.0.1` (which means the calling container). The loopback port bindings
above are for host development; a remote deployment needs its own private
network, access control, and TLS gateway.

Inspect a failure with `podman logs --tail 100 CONTAINER_NAME`. Stop the examples
with `podman stop osii-tesseract osii-csv-table-extractor osii-collection-table-enricher`;
`podman start CONTAINER_NAME` reuses them. To adopt a rebuilt image, stop and
remove only the named tool container, then repeat its `podman run` command.

## Push the starter images to Quay

Create the two Quay repositories in your namespace (choose private/public
deliberately), or confirm your account has permission to create them on push.
Login prompts for registry credentials; never put them in these commands or Git.
Run each push only after its build and smoke test succeed:

```sh
podman login quay.io
podman push "${TOOLBOX_PREFIX}-tesseract:${TOOLBOX_TAG}"
podman push "${TOOLBOX_PREFIX}-tabular-dataset-processors:${TOOLBOX_TAG}"
```

On another machine, set the same two variables, run `podman login quay.io` for
private images, then:

```sh
podman pull "${TOOLBOX_PREFIX}-tesseract:${TOOLBOX_TAG}"
podman pull "${TOOLBOX_PREFIX}-tabular-dataset-processors:${TOOLBOX_TAG}"
```

Use the same `podman run` commands above. The root Compose deployment already
references `osii-tesseract` via `OSII_IMAGE_PREFIX` / `OSII_IMAGE_TAG`; use matching
values for that deployment. The Toolbox builds/pushes are explicit and separate
from Core's existing three-image `make build` / `push-release` workflow.

Before a real release, review licenses, scan images/dependencies, and record
image digests. Existing dependency pins are carried over from the Tool Chest,
not a declaration that they have passed a current security audit. The commands
here are a publishing starter, not a security certification.

Reference: [Podman build/platform options](https://docs.podman.io/en/stable/markdown/podman-build.1.html),
[Podman push](https://docs.podman.io/en/stable/markdown/podman-push.1.html), and
[Quay repository permissions and push/pull](https://docs.quay.io/guides/pushpull.html).

## Optional model-heavy images

Skip this section when Ollama or your existing embedding endpoint is sufficient.
Neither Python stack is added to OSII's normal environment or lockfile. There
are no model files in Git; local `models/` folders are ignored. Rebuild the
semantic index when changing provider, model, or dimensions.

### MiniLM: embeds its model during the build

This existing implementation installs PyTorch/Sentence Transformers and downloads
`sentence-transformers/all-MiniLM-L6-v2` from Hugging Face **at build time**.
It consumes substantially more disk/RAM than the starter tools. Review and
approve those dependencies and model provenance independently; do not build
it if Hugging Face access is disallowed. The finished image uses offline mode.

```sh
podman build --format docker --platform linux/amd64 -t "${TOOLBOX_PREFIX}-minilm-embedding:${TOOLBOX_TAG}" toolbox/minilm-embedding-service
podman run -d --name osii-minilm -p 127.0.0.1:8086:8085 "${TOOLBOX_PREFIX}-minilm-embedding:${TOOLBOX_TAG}"
```

Check <http://127.0.0.1:8086/health> and `/docs`, then configure **Setup → AI model
connections → Other OpenAI-compatible endpoint**, base URL
`http://127.0.0.1:8086/v1`, embedding model
`sentence-transformers/all-MiniLM-L6-v2`. Enter the model manually: this service
does not provide `/models` discovery or chat. It does not require an API key.
Do **not** register it as a Processor API URL. After validation:

```sh
podman push "${TOOLBOX_PREFIX}-minilm-embedding:${TOOLBOX_TAG}"
```

### Model2Vec: mount an approved, staged model

The image installs the experimental Model2Vec dependency but **no model**. Stage
your approved complete model directory outside Git. Without it startup fails
explicitly, instead of silently providing hashing vectors.

```sh
podman build --format docker --platform linux/amd64 -f toolbox/model2vec-embedder/Dockerfile -t "${TOOLBOX_PREFIX}-model2vec-embedder:${TOOLBOX_TAG}" .
```

Set the staged directory in your shell (use the actual path):

```bash
TOOLBOX_MODEL_DIR="/absolute/path/to/approved-model"
```

```powershell
$TOOLBOX_MODEL_DIR = "C:/Models/approved-model"
```

Then, in either shell:

```sh
podman run -d --name osii-model2vec -p 127.0.0.1:8087:8085 --mount "type=bind,source=${TOOLBOX_MODEL_DIR},target=/models/model2vec,readonly" "${TOOLBOX_PREFIX}-model2vec-embedder:${TOOLBOX_TAG}"
```

Register `http://127.0.0.1:8087` as a Processor API endpoint; check its descriptor
is `local.model2vec`. The selected model directory must be readable inside the
Podman machine. After testing with that model:

```sh
podman push "${TOOLBOX_PREFIX}-model2vec-embedder:${TOOLBOX_TAG}"
```

## Develop without containers / export to another repository

Per-tool READMEs include isolated host and test commands. Tesseract needs its
native executable installed on the host; CSV/table processing needs only Python.
Do not install all tools into one environment: their dependencies and Python
`app` modules can conflict.

To export source plus the shared SDK without environments, caches, or weights:

```sh
uv run --no-project --python 3.11 python scripts/export_components.py --components toolbox --output ../osii-toolbox-export
```

Use the new `../osii-toolbox-export/toolbox/` as the receiving repository root;
it contains `toolbox/` and `packages/` so the root-context build commands above
still work. The original sibling checkout's Git history and local environments
were not imported. Its moved source is now maintained here; no private Shirty
package or separate Shirty bridge is included.
