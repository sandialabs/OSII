# Publish OSII images to Quay

The normal packaged OSII release now consists of four image artifacts:

| Image suffix | Runs |
|---|---|
| `-core` | API or worker, selected by the container command |
| `-dashboard` | Static dashboard and API proxy |
| `-chat` | Grounded chat service |
| `-baseline-processors` | Extractor, synthesizer, embedder, enricher, or model bridge |

The baseline image has selectable commands rather than combining service APIs
into one process. Compose starts five independently replaceable containers from
that one immutable image. This preserves health checks, scaling, service
boundaries, and later separation into repositories while avoiding five nearly
identical Quay repositories.

MCP is an optional fifth OSII image. Tika uses its upstream Apache image.
Tesseract OCR and example processors remain optional builds and are not part of
the four-image normal release. Ollama is separately managed and OSII publishes
no model weights.

## Build the four release images

Use a version tag rather than relying only on `latest`:

```bash
cd /path/to/osii
make build-release \
  OSII_IMAGE_PREFIX=quay.io/your-organization/osii \
  OSII_IMAGE_TAG=0.1.0
```

This produces:

```text
quay.io/your-organization/osii-core:0.1.0
quay.io/your-organization/osii-dashboard:0.1.0
quay.io/your-organization/osii-chat:0.1.0
quay.io/your-organization/osii-baseline-processors:0.1.0
```

On Windows PowerShell:

```powershell
.\scripts\osii.ps1 build-release `
  -ImagePrefix quay.io/your-organization/osii `
  -ImageTag 0.1.0
```

## Push after review

Authenticate, inspect the four local tags, and push intentionally:

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
authorized for all four target names.

## Run the published images

Set the same two variables in `.env`, then use the normal command:

```dotenv
OSII_IMAGE_PREFIX=quay.io/your-organization/osii
OSII_IMAGE_TAG=0.1.0
```

```bash
make run
```

Compose uses the shared core image for API and worker and the shared baseline
image for all five capability processes. `make run` pulls missing tagged images
but passes `--no-build`, so a deployment never quietly builds from source.

Container count and image count are intentionally different: `make run` starts
nine containers but pulls only four OSII image artifacts. It does not silently
add MCP or OCR. Enable those deployment profiles explicitly after publishing
their optional images; Tika continues to come from Apache's upstream registry.
