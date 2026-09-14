# OSII Toolbox: deploy and publish

Specialized tools live here, **inside the main OSII repository**. You need only
one checkout. Every tool is optional, independently buildable, and started only
when a deployment selects it. None are built or started by the default
`make build`, `make run`, or `make dev` workflow. The dependable full-page
Tesseract extractor is not a Toolbox tool; it is included in the shared
`osii-baseline-processors` image.
The shared Processor SDK stays in `osii-core/processor-sdk/`.

## Pick the capability you need

| Folder / image suffix | Release policy | What it does | API | Host port in this guide |
|---|---|---|---|---|
| [osii-tesseract](osii-tesseract/README.md) / `-tesseract-opencv` | Experimental | OpenCV region detection + Tesseract OCR; text and page bounding boxes | Processor API extractor | 8081 |
| [tabular-dataset-processors](tabular-dataset-processors/README.md) / `-tabular` | Optional | CSV rows as standard tables; collection tables retaining row provenance | Processor API extractor and enricher; **one image, two processes** | 8097 / 8098 |
| [minilm-embedding-service](minilm-embedding-service/README.md) / `-minilm` | Optional | CPU MiniLM semantic embeddings, 384 dimensions | OpenAI-compatible `/v1/embeddings`, **not** Processor API | 8086 |
| [model2vec-embedder](model2vec-embedder/README.md) / `-model2vec` | Optional | Experimental semantic embeddings from an explicitly staged model | Processor API embedder | 8087 |

That is **four possible images, five containers if you run every capability**.
You need not publish or run all of them. Apache Tika is an upstream image and
Ollama is a separately managed provider; neither is copied into this Toolbox.
Core and its normal model connections remain unchanged.

All OSII-authored Toolbox Dockerfiles use the same RHEL/UBI base and install
their fixed application Python from RHEL packages. They default to public UBI 9 and
accept `--build-arg OSII_BASE_IMAGE=registry.example/approved/rhel9/python-latest`.
Tesseract builds
its pinned native dependencies in a UBI builder stage because public UBI
repositories do not carry Tesseract RPMs. An approved corporate artifact
mirror can replace the three source locations documented in
[Corporate pilot images and Quay releases](../docs/operations/publishing-images.md#portable-rhel-family-base-images).
These switches alter packaging only; they do not change Processor API behavior.

Every OSII-authored Toolbox Dockerfile also accepts the optional
`osii_ca_bundle` Podman build secret used by the root build workflow. Corporate
CA files remain outside Git and are installed into private images only. See
[Inject local corporate certificate authorities](../docs/operations/publishing-images.md#inject-local-corporate-certificate-authorities)
for validation, trust, and rotation behavior before adapting the root build
flags to a standalone Toolbox build.

## One workflow for every tool

Run from the **OSII repository root**, not this folder. First list the tools:

```bash
make toolbox-list
```

Build one native-architecture image with the same corporate base, certificate,
and proxy controls as the main release:

```bash
make toolbox-build TOOL=tesseract-opencv \
  OSII_IMAGE_PREFIX=quay.io/your-namespace/osii \
  OSII_IMAGE_TAG=0.1.0 \
  OSII_BASE_IMAGE=registry.example/approved/rhel9
```

Push it after testing:

```bash
make toolbox-push TOOL=tesseract-opencv \
  OSII_IMAGE_PREFIX=quay.io/your-namespace/osii \
  OSII_IMAGE_TAG=0.1.0
```

On a deployment computer, pull and run that tool without rebuilding:

```bash
make toolbox-run TOOL=tesseract-opencv \
  OSII_IMAGE_PREFIX=quay.io/your-namespace/osii \
  OSII_IMAGE_TAG=0.1.0
```

Use `TOOL=minilm`, `TOOL=model2vec`, or `TOOL=tabular` for the other images.
The tabular command starts its extractor and enricher processes together. Stop
the selected tool with `make toolbox-stop TOOL=tesseract-opencv`.

PowerShell uses the same command names and `-Tool`:

```powershell
.\scripts\osii.ps1 toolbox-build -Tool tesseract-opencv `
  -ImagePrefix quay.io/your-namespace/osii -ImageTag 0.1.0
.\scripts\osii.ps1 toolbox-push -Tool tesseract-opencv `
  -ImagePrefix quay.io/your-namespace/osii -ImageTag 0.1.0
.\scripts\osii.ps1 toolbox-run -Tool tesseract-opencv `
  -ImagePrefix quay.io/your-namespace/osii -ImageTag 0.1.0
```

To build and publish all four Toolbox images for both Linux architectures:

```bash
make toolbox-publish-multiarch \
  OSII_IMAGE_PREFIX=quay.io/your-namespace/osii \
  OSII_IMAGE_TAG=0.1.0 \
  OSII_BASE_IMAGE=registry.example/approved/rhel9
```

## Connect and check a running tool

These launch only the selected optional tools, not OSII itself. Leave `make dev`
or `.\scripts\osii.ps1 dev` running in its own terminal.

Open each service's `/health`, `/v1/descriptor`, and `/docs`, for example
<http://127.0.0.1:8097/docs>. Health confirms the HTTP process is up, not
extraction accuracy; exercise one document in `/docs` or Intake before
publishing.

In **Setup**, register these as custom **Processor API** endpoints, test them,
then select the extractor/routing or enrichment you want. Alternatively append
the URLs to `OSII_PROCESSORS` in the ignored root `.env` and restart OSII:

```dotenv
# Preserve any existing URLs too; this is an example, not an append operation.
OSII_PROCESSORS=http://127.0.0.1:8097,http://127.0.0.1:8098
```

Do not mount `.osii` or your document directories into these containers. Core
sends the selected bytes/text and saves returned artifacts. Container-to-container
connections must use shared-network service names or a reachable host address,
not `127.0.0.1` (which means the calling container). The loopback port bindings
above are for host development; a remote deployment needs its own private
network, access control, and TLS gateway.

Inspect running services with `podman-compose ps` and failures with
`podman-compose logs SERVICE`. The service names are `tesseract-opencv`, `minilm`,
`model2vec`, `tabular-extractor`, and `tabular-enricher`.

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

Build and run it with `make toolbox-build TOOL=minilm` and
`make toolbox-run TOOL=minilm`, supplying the same image prefix, tag, base,
certificate, and proxy options shown above.

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

Stage the model in `osii-data/models/model2vec`, or set its location explicitly:

```bash
MODEL2VEC_MODEL_DIR="/absolute/path/to/approved-model" make toolbox-run TOOL=model2vec
```

```powershell
$ModelDir = "C:\Models\approved-model"
.\scripts\osii.ps1 toolbox-run -Tool model2vec -ModelDir $ModelDir
```

Register `http://127.0.0.1:8087` as a Processor API endpoint; check its descriptor
is `local.model2vec`. The selected model directory must be readable inside the
Podman machine.

## Develop without containers / export to another repository

Per-tool READMEs include isolated host and test commands. Tesseract needs its
native executable installed on the host; CSV/table processing needs only Python.
Do not install all tools into one environment: their dependencies and Python
`app` modules can conflict.

To export source plus the shared SDK without environments, caches, or weights:

```sh
uv run --no-project --python 3.12 python scripts/export_components.py --components osii-toolbox --output ../osii-toolbox-export
```

Use the new `../osii-toolbox-export/osii-toolbox/` as the receiving repository root;
it contains `osii-toolbox/` and `osii-core/processor-sdk/` so the root-context build commands above
still work. The original sibling checkout's Git history and local environments
were not imported. Its moved source is now maintained here; no private provider
package or separate proprietary bridge is included.
