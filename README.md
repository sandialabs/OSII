# The On-Store Intelligence Index (OSII)

OSII builds a grounded, inspectable intelligence layer over a user's own files.
People can browse, search, and chat with their corpus today; AI agents can use
the same scopes, artifacts, provenance, and retrieval APIs for detailed future
workflows.

The project also supports domain extension without a core fork. A subject
matter expert can package an extractor, synthesizer, embedder, or enricher as a
small container. For example, an experimental team can process thousands of
run folders into a standard table artifact that is immediately visible in the
dashboard and available to agents.

[Read the documentation](https://heidikmkv.github.io/osii/) ·
[Browse the documentation on GitHub](docs/index.md)

## Getting started

OSII uses Podman for packaged deployment and for system-level development
dependencies. The development shortcut runs editable application code directly
on the host, so Python changes reload and dashboard changes appear immediately.

### 1. Choose where your files live

By default, OSII looks in this folder inside the downloaded project:

```text
osii-data/
└── source/       Put the files and folders you want OSII to process here
```

On macOS or Linux, create it and initialize your settings with:

```bash
cd /path/to/osii
mkdir -p osii-data/source
cp .env.example .env
```

On Windows PowerShell:

```powershell
cd C:\path\to\osii
New-Item -ItemType Directory -Force osii-data\source
Copy-Item .env.example .env
```

You can now drag files into the newly created `osii-data/source` folder using
Finder or File Explorer. Files placed in the repository root are intentionally
not shown; this avoids treating OSII's own code and configuration as your
corpus.

OSII mounts `source` read-only: it can read your originals but cannot modify or
delete them. The `osii-data` folder is ignored by Git, so your documents will
not accidentally be included in a commit.

You can instead use an existing folder anywhere on your computer. Open `.env`
in a text editor and set its absolute path:

```dotenv
OSII_SOURCE_DIR=/Users/your-name/Documents/my-files
```

On Windows, use a forward-slash path such as:

```dotenv
OSII_SOURCE_DIR=C:/Users/your-name/Documents/my-files
```

Files added with the dashboard's **Upload files** button are stored separately
in a container-managed upload volume. OSII's generated database, extracted
text, queue status, and indexes are also kept separately from your originals.

### 2. Develop OSII with live reload

Make sure the Podman machine is running on macOS or Windows:

```bash
podman machine start
```

On macOS or Linux, start the editable stack:

```bash
cd /path/to/osii
make dev
```

`make dev` starts only Tika and Tesseract in Podman. It runs the API, worker,
local chat service, and Vite dashboard from source. The launcher checks ports
and dependencies, reloads backend services when Python changes, and lets Vite
update the browser as frontend code changes. Generated development data stays
under `osii-data/`.

Embeddings are optional during normal development. Start the same editable
stack with the local Jina service only when testing semantic search:

```bash
make dev-embeddings
```

On Windows, use `.\scripts\osii.ps1 dev-embeddings`. The first embedding start
downloads the model into `osii-data/models/`; later starts reuse it.

On Windows PowerShell, use the equivalent launcher:

```powershell
cd C:\path\to\osii
.\scripts\osii.ps1 dev
```

The first development startup may take longer while dependencies are checked.
Later starts reuse them. When the terminal output settles, open:

- **OSII dashboard:** <http://localhost:5173>
- **Backend status:** <http://localhost:8511/health>

In the dashboard, select **Processing** in the sidebar. Choose files from the
shared folder or use **Upload files**, select the operations you want, and
press **Start processing**. Progress and recent messages appear on the same
page.

Keep the terminal window open while using OSII. Stop host processes with
<kbd>Ctrl</kbd>+<kbd>C</kbd>. Stop the supporting containers with `make down`
or `.\scripts\osii.ps1 down`.

### Run the packaged container stack

Use the deployment-style stack when testing images rather than editing code:

```bash
make build
make run
```

On Windows PowerShell:

```powershell
.\scripts\osii.ps1 build
.\scripts\osii.ps1 run
```

`make run` never rebuilds images. Use `make containers-dev` or
`.\scripts\osii.ps1 containers-dev` when you intentionally want to rebuild and
run the normal integrated container stack.

### Useful shortcuts

- `make dev-embeddings` / `.\scripts\osii.ps1 dev-embeddings`: run editable
  OSII with the optional local embedding service.
- `make dev-services` / `.\scripts\osii.ps1 dev-services`: start only the
  Podman services needed by bare-metal development.
- `make dev-examples` / `.\scripts\osii.ps1 dev-examples`: run editable OSII
  plus the example table enricher.
- `make dev-all` / `.\scripts\osii.ps1 dev-all`: include optional agents,
  embeddings, Ollama, and all example services in containers.
- `make containers-dev` / `.\scripts\osii.ps1 containers-dev`: rebuild and
  run the normal deployment-style container stack.
- `make logs` / `.\scripts\osii.ps1 logs`: follow service logs.
- `make down` / `.\scripts\osii.ps1 down`: stop the stack without deleting
  your data volume.
- [Export components for separate corporate repositories](docs/operations/component-export.md).

Docker is supported as an override when it is your local container runtime:

```bash
make COMPOSE='docker compose' dev
```

```powershell
.\scripts\osii.ps1 dev -Runtime Docker
```

See the [documentation index](docs/index.md) for guided paths through usage,
architecture, extension development, operations, and API reference.

Important documentation:

- [Extend OSII](docs/extending/index.md)
- [Processor API v1](docs/reference/processor-api/index.md)
- [Standard artifact formats](docs/reference/processor-api/standard-artifacts.md)
- [Architecture](docs/concepts/architecture.md)
- [Local operation](docs/operations/local-first.md)

The repository currently includes:

- a backend for creating local OSII databases from source collections
- a REST API for serving OSII content, search, and derived artifacts
- a frontend for browsing and inspecting the resulting data
- supporting services for OCR and chat/RAG workflows
- a versioned processor SDK and copyable extension examples

## What this does

At a high level, the system works in three stages:

1. ingest a source file collection into a local structured OSII database
2. serve that database through a backend API
3. browse, inspect, search, and analyze the collection through the frontend

## Local-first operation

Browsing, lexical retrieval, extractive grounded chat, baseline synthesis, and
baseline enrichment can run without a model connection. Bundled Tika,
Tesseract, and Jina containers provide local extraction/OCR and embeddings.
Connected model services enhance these capabilities but are not required for
the basic user experience.

The repository remains under active development. Processor API v1 is the
compatibility boundary for new extensions.

## Repository contents

The monorepo currently contains components such as:

- OSII backend
- frontend dashboard / data viewer
- OCR service integrations
- chat / RAG support
- MCP and related tooling

## Typical usage

### 1. Build a local OSII database
Use the backend CLI to process a source collection into `.osii`.
For a step-by-step, code-first walkthrough, use the
[Jupytext-ready Python demonstrations](osii-demo-notebooks/README.md).

### 2. Start the backend API
Run the backend FastAPI service to expose the OSII store over REST.

### 3. Start the frontend
Run the frontend to browse and inspect the collection.

## Work in progress

This is an open development repository. Expect:

- ongoing refactors
- evolving APIs
- incomplete documentation in some areas
- experimental features
