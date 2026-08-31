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
[Browse the documentation on GitHub](docs/index.md) ·
[Follow the Python walkthrough](osii-demo-notebooks/README.md)

## Getting started

Choose the path that matches your goal:

- **Use a corporate pilot release:** follow [Corporate pilot images and Quay releases](docs/operations/publishing-images.md). It runs the supported bundle from approved images.
- **Develop or evaluate OSII from source:** follow the steps below. This path runs editable code and reloads Python/dashboard changes.
- **Build a processor:** start with [Extend OSII](docs/extending/index.md); a processor is an optional compute service, not a fork of core storage.

OSII uses Podman for packaged deployment and system-level development dependencies.

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

A mounted shared or network drive works the same way; point
`OSII_SOURCE_DIR` at its mounted path (for example `S:/project-files`) and make
sure the account running OSII can read it. Intake intentionally browses only
inside this configured root rather than exposing the whole host filesystem.

Files added with the dashboard's **Upload files** button are stored separately.
Canonical extracted text and provenance stay as inspectable `.osii` files;
queue state and the rebuildable SQLite catalog stay under `.osii/state/`.

### 2. Develop OSII with live reload

On macOS or Linux, start the editable stack:

```bash
cd /path/to/osii
make dev
```

`make dev` requires no container runtime or model download. It starts the
dashboard, backend, worker, MCP server, and OSII's small model-free processing
services directly from source. The included workflow can read ordinary
text-layer PDFs and Office files, browse them, enrich them, and search them
with BM25.

Open **Setup** in the dashboard for anything optional. From one screen you can:

- connect Shirty, Ollama, or another OpenAI-compatible endpoint;
- paste and save an API key in the ignored repository-root `.env`;
- select separate language and embedding models;
- start Apache Tika through Podman or Docker;
- start OSII's OCR wrapper after installing the Tesseract executable.

OSII does not install or start the separate Ollama application, Tesseract
executable, or container runtime. Setup detects those prerequisites, performs
the remaining launch or connection step, and keeps technical details behind
**Advanced & diagnostics**. BM25 remains available whenever no embedding model
is connected.

On Windows PowerShell, use the equivalent launcher:

```powershell
cd C:\path\to\osii
.\scripts\osii.ps1 dev
```

The first development startup may take longer while dependencies are checked.
Later starts reuse the ignored `osii-env` Python environment. The launcher
waits for the backend health check before starting the dashboard, so Windows
users do not land in a half-started interface filled with proxy errors. If the
API fails, the dashboard stays stopped and the terminal identifies the service
that exited or timed out. When the terminal output settles, open:

- **OSII dashboard:** <http://localhost:5173>
- **Backend status:** <http://localhost:8511/health>

Service URLs and live API documentation are listed under **Setup → Advanced &
diagnostics** and in the [REST API reference](docs/reference/api/index.md).

On Windows, Ctrl+C shuts down each complete Uvicorn, watchfiles, MCP, and Vite
process tree. If an older checkout already left development processes behind,
list and stop only listeners on OSII's host-development ports before restarting:

```powershell
$ports = 5173,8022,8085,8092,8093,8094,8095,8511
$listeners = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
  Where-Object { $ports -contains $_.LocalPort }
$listeners | Select-Object LocalPort,OwningProcess,
  @{Name="Process";Expression={(Get-Process -Id $_.OwningProcess).ProcessName}}
$listeners.OwningProcess | Sort-Object -Unique |
  ForEach-Object { taskkill.exe /PID $_ /T /F }
```

This deliberately excludes Ollama's port 11434 and optional OCR/container
ports.

In the dashboard, select **Intake** in the first sidebar section. **Add files**
tests required tools and shows the extractor selected for each matched file
type. **Process library** adds embeddings, summaries, enrichments, or a better
extraction to existing documents without repeating unrelated work.
**Activity** keeps run history out of the setup forms. The entire shared volume
is the default scope; file-type and glob rules narrow it rather than replacing
it. Files are processed sequentially and appear under **Files** as each
extraction completes.

Re-extraction is versioned. A better extractor can be saved beside the current
result or made primary while preserving the previous version. See
[Extraction versions and downstream lineage](docs/reference/extraction-versions.md).

With an Ollama synthesis model selected, open a document's **Wiki** tab or an
individual collection to generate a grounded LLM wiki as a standard enrichment
artifact. The model runs outside OSII; the portable Markdown and provenance are
saved inside `.osii`. See [Generate an LLM wiki](docs/tutorials/llm-wiki.md).

The document **Enrichments** tab and collection **Derived artifacts** section
also include model-free examples for a top-20 noun/adjective n-gram keyword
table and a grounded named-entity candidate list. See
[Example keyword and entity enrichments](docs/tutorials/example-enrichments.md).

Search and Chat retain up to 20 recent searches or prompts in the current
browser so those pages remain useful between visits. Only the prompt, scope,
time, and search mode are saved—never results, answers, or citations—and each
entry or the complete browser-local history can be deleted. Saved root and
collection keyword snapshots also provide one-click searches and grounded
question starters. The Home page's collapsed **Library Insights** section
exposes root-level wikis, tables, entity lists, and standard knowledge graphs
without adding another service or storage authority.

Use **Labels & Tags** on a document to store portable sensitivity awareness,
handling notes, and plain-text tags in its canonical object sidecar. These
markings are metadata, not access controls. A collection can be exported as a
manifest/checksum-validated OSII package and merged from **Collections** on
another system; duplicate file IDs retain local data and union their labels.
**Delete File Data** always shows the affected collections, folders, aggregate
products, source file, and indexes before requiring exact confirmation. See
[Sensitive data, transfer, and deletion](docs/operations/sensitive-data.md).

Open **Setup** when you want to add OCR, broader format support, an AI
connection, or a custom Processor API service. The normal view answers whether
OSII can read documents, whether AI is connected, and which extraction,
synthesis, embedding, and enrichment methods Intake will use. Ports, health
tests, schemas, custom service registration, and logs are available only under
**Advanced & diagnostics**.

Keep the terminal window open while using OSII. Stop host processes with
<kbd>Ctrl</kbd>+<kbd>C</kbd>. There are no containers to stop after `make dev`.

### Test locally built images

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
run the integrated stack with optional MCP and OCR. The normal `run` command
starts the eight application/baseline containers and does not silently require
optional MCP or OCR images.

The normal release publishes three OSII image artifacts: core (shared by API,
worker, and chat), dashboard, and baseline processors. The extractor,
synthesizer, embedder, enricher, and model-provider bridge remain separate
containers but select commands from the same compact baseline image. See
[Publish OSII images to Quay](docs/operations/publishing-images.md).

### Useful shortcuts

- `make dev` / `make dev-host` / `.\scripts\osii.ps1 dev`: run the complete
  editable development stack without containers.
- `make dev-core` / `.\scripts\osii.ps1 dev-core`: run application services
  without processors for external-integration testing.
- `make dev-ollama` / `.\scripts\osii.ps1 dev-ollama`: explicit alias for the
  normal Ollama-first development profile.
- `make dev-commercial` / `.\scripts\osii.ps1 dev-commercial`: use a personal,
  OpenAI-compatible endpoint for grounded chat and synthesis, while retaining
  local extractive and lexical fallback methods. See [commercial vLLM testing](docs/operations/commercial-vllm-testing.md).
- `make dev-corporate` / `.\scripts\osii.ps1 dev-corporate`: prefer Shirty's
  OpenAI-compatible chat, synthesis, and embedding APIs while keeping document
  extraction local and retaining BM25/extractive fallbacks.
- `make dev-extractor`, `dev-synthesizer`, `dev-embedder`, or `dev-enricher`
  (and matching PowerShell commands): run one processor independently.
- `make dev-model-bridge` / `.\scripts\osii.ps1 dev-model-bridge`: run only the
  HTTP-only Ollama/Shirty/OpenAI-compatible provider adapter.
- `make dev-ocr-host` / `.\scripts\osii.ps1 dev-ocr-host`: run the optional
  OpenCV/Tesseract OCR service directly on the host, with its tuning UI at
  `http://localhost:8080/demo`.
- `make dev-tika` / `.\scripts\osii.ps1 dev-tika`: start only Apache Tika in
  Podman. Run it in a second terminal beside `make dev` to keep all OSII code
  editable on the host.
- `make dev-containers` / `.\scripts\osii.ps1 dev-containers`: run application
  services from source while Tika and Tesseract run in Podman for deployment
  parity.
- `make dev-containers-insecure`: the same hybrid workflow with Podman registry
  TLS verification disabled for image pulls and builds. On Windows use
  `.\scripts\osii.ps1 dev-containers -InsecureRegistries`. This is an explicit
  trust decision; prefer verified registry certificates when available.
- `make dev-services` / `.\scripts\osii.ps1 dev-services`: start only the
  Podman OCR services used by `dev-containers`.
- `make dev-examples` / `.\scripts\osii.ps1 dev-examples`: run editable OSII
  plus the example table enricher.
- `make dev-all` / `.\scripts\osii.ps1 dev-all`: include optional agents, OCR,
  and all example services in containers. Ollama remains separately managed.
- `make containers-dev` / `.\scripts\osii.ps1 containers-dev`: rebuild and
  run the normal deployment-style container stack.
- `make build-release` / `.\scripts\osii.ps1 build-release`: build the three
  normal publishable images exactly once each.
- `make push-release` / `.\scripts\osii.ps1 push-release`: push those three
  explicitly tagged images after a non-local registry prefix is supplied.
- `make logs` / `.\scripts\osii.ps1 logs`: follow service logs.
- `make down` / `.\scripts\osii.ps1 down`: stop the stack without deleting
  your data volume.
- `make doctor` / `.\scripts\osii.ps1 doctor`: report generated environments,
  model caches, `node_modules`, OSII data, and container storage without deleting anything.
- `make catalog-rebuild` and `make catalog-verify` (with matching PowerShell
  commands): manage the disposable `.osii/state/catalog.sqlite3` read index.
- [Export components for separate corporate repositories](docs/operations/component-export.md).

Docker is supported as an override when it is your local container runtime:

```bash
make COMPOSE='docker compose' dev-containers
```

```powershell
.\scripts\osii.ps1 dev-containers -Runtime Docker
```

See the [documentation index](docs/index.md) for three short starting paths.
The remaining pages are task-oriented reference material; nobody needs to read
the documentation tree from beginning to end. Common next steps are:

- [Python module walkthrough](osii-demo-notebooks/README.md)
- [Extend OSII](docs/extending/index.md)
- [Processor API v1](docs/reference/processor-api/index.md)
- [Standard artifact formats](docs/reference/processor-api/standard-artifacts.md)
- [Architecture](docs/concepts/architecture.md)
- [Local operation](docs/operations/local-first.md)
- [Guaranteed local processors](docs/operations/local-processors.md)
- [Sensitive data, transfer, and deletion](docs/operations/sensitive-data.md)

The repository currently includes:

- a backend for creating local OSII databases from source collections
- a REST API for serving OSII content, search, and derived artifacts
- a frontend for browsing and inspecting the resulting data
- Core-owned RAG orchestration plus optional OCR and model-provider services
- a versioned processor SDK and copyable extension examples

## What this does

At a high level, the system works in three stages:

1. ingest a source file collection into a local structured OSII database
2. serve that database through a backend API
3. browse, inspect, search, and analyze the collection through the frontend

## Local-first operation

Browsing, lexical retrieval, hashing-vector retrieval, extractive grounded
chat, baseline synthesis, and baseline enrichment run without a model
connection. Tika and Tesseract remain optional OCR/deployment services. Ollama,
OpenAI-compatible services, Shirty, and domain processors enhance capabilities
without becoming dependencies of the basic user experience.

Retrieval defaults to sentence-aligned 768-character chunks with roughly 128
characters of overlap. Intake exposes these settings, while BM25 and semantic
retrieval share the same chunk manifest and grounded source offsets. See
[retrieval chunking and overlap](docs/concepts/retrieval-chunking.md).

The repository remains under active development. Processor API v1 is the
compatibility boundary for new extensions.

## Repository contents

The monorepo currently contains components such as:

- OSII backend
- frontend dashboard / data viewer
- OCR service integrations
- Core-owned grounded chat / RAG support
- MCP and related tooling

## Typical usage

### 1. Build a local OSII database
Use the backend CLI to process a source collection into `.osii`.
For a comprehensive but small step-by-step walkthrough, use the
[Jupytext-ready Python demonstrations](osii-demo-notebooks/README.md). Plain
Python files are canonical; `manage_notebooks.py` converts the complete set to
or from notebooks without making notebook JSON the normal review format.

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
