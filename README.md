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

Files added with the dashboard's **Upload files** button are stored separately.
Canonical extracted text and provenance stay as inspectable `.osii` files;
queue state and the rebuildable SQLite catalog stay under `.osii/state/`.

### 2. Develop OSII with live reload

On macOS or Linux, start the editable stack:

```bash
cd /path/to/osii
make dev
```

`make dev` requires no container runtime or preexisting model download. It runs the API,
worker, local chat, MCP server, dashboard, and four independent Processor API
services directly from source: native-text extraction, cited extractive
previews, 384-dimensional lexical hashing embeddings, and statistics/keyword
enrichment. Scanned PDFs still require optional OCR. The launcher checks ports and dependencies,
reloads backend services when source changes, and keeps generated data under
`osii-data/`.

OSII first tries a separately installed Ollama service with `all-minilm` for
semantic embeddings and Meta `llama3.2:1b` for chat and synthesis. Open
**Tools → Model providers** to see installed models and explicitly download
either approved starter model when missing. OSII bundles neither Ollama nor
model weights. Hashing, BM25, and extractive chat remain the automatic
model-free fallbacks.

On Windows PowerShell, use the equivalent launcher:

```powershell
cd C:\path\to\osii
.\scripts\osii.ps1 dev
```

The first development startup may take longer while dependencies are checked.
Later starts reuse the ignored `osii-env` Python environment. When the terminal
output settles, open:

- **OSII dashboard:** <http://localhost:5173>
- **Backend status:** <http://localhost:8511/health>
- **Extractor docs:** <http://localhost:8092/docs>
- **Synthesizer docs:** <http://localhost:8093/docs>
- **Embedder docs:** <http://localhost:8085/docs>
- **Enricher docs:** <http://localhost:8094/docs>
- **Model-provider bridge docs:** <http://localhost:8095/docs>
- **Chat health/docs:** <http://localhost:8611/health> · <http://localhost:8611/docs>
- **MCP server:** <http://localhost:8022/mcp>

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

Open **Tools** before the first intake. Its Overview, Model providers, Local
capabilities, and Processor endpoints submenus keep setup details separate.
For a domain
processor running on the host, use a base URL such as
`http://127.0.0.1:8091`; a packaged API container should use the processor's
Compose service name or `host.containers.internal` for a host service. Run
**Health**, then **Test**, and return to Intake to select **Retest tools**.

Keep the terminal window open while using OSII. Stop host processes with
<kbd>Ctrl</kbd>+<kbd>C</kbd>. There are no containers to stop after `make dev`.

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

- `make dev` / `make dev-host` / `.\scripts\osii.ps1 dev`: run the complete
  editable development stack without containers.
- `make dev-core` / `.\scripts\osii.ps1 dev-core`: run application services
  without processors for external-integration testing.
- `make dev-ollama` / `.\scripts\osii.ps1 dev-ollama`: explicit alias for the
  normal Ollama-first development profile.
- `make dev-corporate` / `.\scripts\osii.ps1 dev-corporate`: prefer the
  separately running Shirty bridge, then Ollama, then extractive fallbacks.
- `make dev-extractor`, `dev-synthesizer`, `dev-embedder`, or `dev-enricher`
  (and matching PowerShell commands): run one processor independently.
- `make dev-model-bridge` / `.\scripts\osii.ps1 dev-model-bridge`: run only the
  HTTP-only Ollama/OpenAI-compatible bridge.
- `make dev-ocr-host` / `.\scripts\osii.ps1 dev-ocr-host`: run the optional
  OpenCV/Tesseract OCR service directly on the host, with its tuning UI at
  `http://localhost:8080/demo`.
- `make dev-containers` / `.\scripts\osii.ps1 dev-containers`: run application
  services from source while Tika and Tesseract run in Podman for deployment
  parity.
- `make dev-services` / `.\scripts\osii.ps1 dev-services`: start only the
  Podman OCR services used by `dev-containers`.
- `make dev-examples` / `.\scripts\osii.ps1 dev-examples`: run editable OSII
  plus the example table enricher.
- `make dev-all` / `.\scripts\osii.ps1 dev-all`: include optional agents, OCR,
  and all example services in containers. Ollama remains separately managed.
- `make containers-dev` / `.\scripts\osii.ps1 containers-dev`: rebuild and
  run the normal deployment-style container stack.
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

See the [documentation index](docs/index.md) for guided paths through usage,
architecture, extension development, operations, and API reference.

Important documentation:

- [Extend OSII](docs/extending/index.md)
- [Processor API v1](docs/reference/processor-api/index.md)
- [Standard artifact formats](docs/reference/processor-api/standard-artifacts.md)
- [Architecture](docs/concepts/architecture.md)
- [Local operation](docs/operations/local-first.md)
- [Guaranteed local processors](docs/operations/local-processors.md)

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
