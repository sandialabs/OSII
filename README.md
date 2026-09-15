# OSII

> **Keep the evidence. Grow the intelligence.**

OSII (the On-Store Intelligence Index) turns a folder of documents and datasets
into a library you can browse, search, enrich, and ask questions about. It runs
locally, works without an AI model, and can use approved AI services when they
are available.

The central promise is simple: **your original files stay where they are and
OSII does not alter them.** OSII records extracted text, tables, summaries,
search indexes, and provenance in a neighboring `.osii` folder. That portable
folder is the *sidecar*: it can be inspected, rebuilt, transferred, or removed
without changing the source material.

[Start the documentation](docs/index.md) ·
[Learn through Python examples](osii-demo-notebooks/README.md) ·
[Understand the architecture](docs/concepts/architecture.md)

## What happens when you use OSII

```text
Your files                         OSII's portable sidecar
----------                         -----------------------
reports, PDFs, CSVs, notes  --->   extracted text and source locations
                                   typed tables, entities, and wikis
                                   provenance and processing history
                                   rebuildable search indexes
                                         |
                                         +--> browse, search, chat, Python,
                                              REST, MCP, and custom processors
```

You interact with the result through the dashboard, Python, REST, or MCP. A
normal first run needs no containers and no model download. Later, you can add
Ollama, an OpenAI-compatible endpoint, OCR, or a domain-specific processor
without replacing the library you already built.

Four ideas guide the project:

- **Grounding before generation.** A model may help interpret material, but it
  is not the source of truth.
- **Canonical files before indexes.** Search indexes and caches make OSII
  fast; they can be rebuilt. The ordinary `.osii` sidecar remains inspectable.
- **Replaceable computation.** You can swap or add extractors, synthesizers,
  embedders, and enrichers without forking the core or changing your originals.
- **One shared vocabulary.** People, scripts, the dashboard, REST clients, and
  agents use the same objects, scopes, artifacts, and provenance.

## Start here: explore the built-in demo

This is the shortest route to seeing OSII work. It uses public demonstration
data and the built-in model-free baseline, so you can postpone decisions about
AI providers, OCR, and containers.

Before starting, install [uv](https://docs.astral.sh/uv/) and Node.js/npm. On
macOS or Linux, you also need `make`. OSII asks uv for its tested Python 3.12
runtime, so you do not need to create or activate a Python environment. No
container runtime or model download is required for this path.

### macOS or Linux

From the repository root:

```bash
make demo
```

### Windows PowerShell

From the repository root:

```powershell
.\scripts\osii.ps1 demo
```

That one command installs a small public example corpus—one PDF and two
datasets—then starts the complete model-free OSII baseline. It creates and
manages the application environment for you. The first run installs Python and
JavaScript packages and can take a few minutes; later runs reuse them. Keep that
terminal open, then visit:

- **Dashboard:** <http://localhost:5173>
- **Backend health:** <http://localhost:8511/health>

In the dashboard, open **Intake**, choose the example files, and process them.
Then explore **Files**, **Search**, and **Collections**. You should be able to
inspect the extracted content and see what OSII created without needing a
model connection.

The baseline includes document extraction, source-excerpt previews, BM25
search, local enrichment, the worker, API, MCP server, and dashboard. Its
ordinary Tesseract service runs once per complete page; on a bare-metal
`make dev` computer, the Tesseract program must first be installed on the host.
The packaged baseline image already contains it. Open **Setup** afterward to
connect Ollama or another AI endpoint, or to add optional Apache Tika. Ollama
is not part of normal startup.

To stop the local stack, return to the terminal and press <kbd>Ctrl</kbd> +
<kbd>C</kbd>.

### Use your own files instead

Put files in `osii-data/source/`, then run `make dev` on macOS/Linux or
`.\scripts\osii.ps1 dev` on Windows. OSII reads that folder but does not modify
or delete its contents. Its derived data is stored beside it in
`osii-data/.osii/`, which is ignored by Git.

To use a source folder elsewhere on your computer, copy `.env.example` to
`.env` and set `OSII_SOURCE_DIR`. The `.env` file is optional for the default
layout. See [local-first operation](docs/operations/local-first.md) for the
cross-platform details and optional capabilities.

### Use a shared drive or Samba share

First connect the share through Windows, Finder, or your Linux desktop so it
appears as an ordinary folder. OSII never asks for or stores the share password.
It reads originals in place—even when they are read-only—and keeps the writable
`.osii` artifacts locally.

macOS or Linux, after mounting the share:

```bash
make dev-shared SHARED_DRIVE_PATH="/Volumes/Team Documents"
```

Windows PowerShell accepts either a mapped drive or a UNC path:

```powershell
.\scripts\osii.ps1 dev-shared `
  -SourceDir '\\server\share\Team Documents'
```

By default, this shared-drive profile stores artifacts under
`osii-data/shared-drive/`. Use `SHARED_DRIVE_DATA=/local/path` on macOS/Linux or
`-RuntimeDir "D:\OSII\team-share"` on Windows to choose another local location.
If the share is disconnected or unreadable, startup explains that directly
instead of creating an empty folder with the same name. Intake shows both the
documents location and the separate artifact location. See [Shared drives and
Samba](docs/operations/shared-drives.md) for packaged-container behavior and
security details.

## Build deployment images with an approved base image

Most people should begin with `make demo` or `make dev` above. Use this section
when you are ready to build the three default OSII images for Podman. These
commands choose the base image for this build only; they do not permanently
change your shell or repository configuration.

If the registry requires authentication, run `podman login quay.asdf.xyz`
first. Then copy and paste the command for your operating system from the
repository root.

### macOS or Linux

Normal inherited proxy behavior:

```bash
make build OSII_BASE_IMAGE=quay.asdf.xyz/dice/rhel9
```

If HTTPS inspection requires local corporate certificates, export only the
public CA certificates to one PEM bundle outside the repository, then run:

```bash
make build \
  OSII_BASE_IMAGE=quay.asdf.xyz/dice/rhel9 \
  OSII_CA_BUNDLE=/absolute/path/to/corporate-roots.pem
```

When the image should retain its corporate certificates but must not inherit
HTTP, HTTPS, FTP, or ALL proxy settings:

```bash
make build \
  OSII_BASE_IMAGE=quay.asdf.xyz/dice/rhel9 \
  OSII_CA_BUNDLE=/absolute/path/to/corporate-roots.pem \
  DISABLE_CONTAINER_PROXIES=true
```

Start images built in direct-network mode with the matching runtime setting:

```bash
make run DISABLE_CONTAINER_PROXIES=true
```

Otherwise, start them normally:

```bash
make run
```

### Windows PowerShell

Normal inherited proxy behavior:

```powershell
.\scripts\osii.ps1 build `
  -BaseImage "quay.asdf.xyz/dice/rhel9"
```

If HTTPS inspection requires local corporate certificates, export only the
public CA certificates to one PEM bundle outside the repository, then run:

```powershell
.\scripts\osii.ps1 build `
  -BaseImage "quay.asdf.xyz/dice/rhel9" `
  -CaBundle "C:\secure\corporate-roots.pem"
```

Keep corporate certificates but disable inherited container proxies:

```powershell
.\scripts\osii.ps1 build `
  -BaseImage "quay.asdf.xyz/dice/rhel9" `
  -CaBundle "C:\secure\corporate-roots.pem" `
  -DisableContainerProxies
```

Start images built in direct-network mode with the matching runtime setting:

```powershell
.\scripts\osii.ps1 run -DisableContainerProxies
```

Otherwise, start them normally:

```powershell
.\scripts\osii.ps1 run
```

The base image must provide `dnf` and access to the required RHEL packages;
each OSII image then installs its tested Python 3.12 runtime. Ordinary
page-by-page Tesseract OCR is compiled into `osii-baseline-processors`; no
fourth image is needed. The experimental OpenCV region OCR and other
`osii-toolbox` images use explicit `toolbox-*` commands. Docker Compose remains available
with `COMPOSE='docker compose'`, but strict removal of proxy settings inherited
from a custom base image is guaranteed only on the supported Podman path. See
[publishing and running images](docs/operations/publishing-images.md) for image
names, tags, registries, and optional Toolbox publication.

`OSII_CA_BUNDLE`/`-CaBundle` is explicit and build-only. OSII validates that the
file contains PEM certificates and no private key, prints its SHA-256
fingerprint, and passes it to Podman as a build secret. The certificate bundle
is installed into the resulting private images so HTTPS works at runtime, but
the source path and file never enter the Git build context. Never supply a
`.pfx`, `.p12`, client certificate, or private key. If you must temporarily
keep the PEM under the repository root, use the ignored `.osii-certs/` folder.

## Choose your next path

| If you want to… | Start here |
| --- | --- |
| Learn the architecture by running small, inspectable examples | [Python demonstration series](osii-demo-notebooks/README.md) |
| Process one file and inspect every resulting sidecar artifact | [Single-file walkthrough](docs/tutorials/single-file.md) |
| Understand why OSII separates core, processors, dashboard, and agents | [Architecture](docs/concepts/architecture.md) |
| Add a custom extractor, synthesizer, embedder, or enricher | [Extend OSII](docs/extending/index.md) |
| Build an external processor against the stable public contract | [Processor API v1](docs/reference/processor-api/index.md) |
| Work with tables and datasets | [Tabular dataset walkthrough](docs/tutorials/tabular-datasets.md) |
| Run packaged deployment images instead of editable source | [Publish and run images](docs/operations/publishing-images.md) |
| Deploy or publish optional dataset and embedding tools, or inspect bundled OCR | [Toolbox: deployment and Quay commands](osii-toolbox/README.md) |
| Find a REST route or schema | [REST API overview](docs/reference/api/index.md) and [OpenAPI schema](osii-core/docs/api/openapi.yaml) |

## How this repository is organized

You do not need to learn the entire monorepo to use OSII. The broad boundaries
are intentional and reflected directly in the root names:

- **`osii-core/`** owns canonical `.osii` persistence, scopes, retrieval, the
  REST API, the worker, and bounded grounded chat.
- **`osii-core/osii/processor_sdk/`** contains the public contracts for custom
  processors, included in the single `osii` Python package. Copyable examples
  and contract tests live in `osii-core/processor-sdk/`.
- **`osii-core/services/`** contains the guaranteed local processor hosts.
  They run automatically during local development and remain independently
  addressable and containerizable.
- **`osii-dashboard/`** and **`osii-mcp/`** are human and agent clients of Core.
- **`osii-launcher/`** is the separately releasable desktop deployment shell
  for non-developers. It owns host-level Podman, Quay, shared-drive, profile,
  and application-lifecycle workflows without moving those concerns into Core.
- **`osii-toolbox/`** contains the optional OpenCV/Tesseract region extractor
  plus dataset and model-backed tools whose dependencies do not belong in
  Core. Ordinary full-page Tesseract lives with the baseline processors.
- **`osii-demo-notebooks/`**, **`docs/`**, and **`scripts/`** provide learning,
  reference, and cross-platform operating support.

For operational commands, see the [CLI cheat sheet](docs/reference/cli.md).
For offline behavior, model connections, OCR, and privacy boundaries, see
[local-first operation](docs/operations/local-first.md) and [sensitive data,
transfer, and deletion](docs/operations/sensitive-data.md).

## What OSII is—and is not

OSII is a research project and a working implementation of grounded,
extensible knowledge infrastructure. It is designed to make the structure and
limits of an interpretation visible—not to claim that a model has solved
understanding.

The repository is actively evolving. The stable compatibility boundary for
external extensions is [Processor API v1](docs/reference/processor-api/index.md).
When in doubt, favor the source material, inspect the sidecar, and follow the
provenance.
