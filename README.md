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

## Getting started — no development experience required

OSII runs as a small group of containers. You do not need to install Python,
JavaScript, a database, or an AI model on your computer.

### 1. Download OSII

Download a release archive when one is available. Otherwise, on the OSII
GitHub page select **Code → Download ZIP**, extract the ZIP, and open the
extracted `osii` folder.

The commands below are entered in a terminal opened in that folder. On macOS,
the Terminal application is under **Applications → Utilities**. On Windows,
use PowerShell.

### 2. Install a container application

Choose either:

- **Docker Desktop**, if your organization already supports Docker; or
- **Podman Desktop**, a free and open-source alternative available for macOS,
  Windows, and Linux.

For Podman, follow the official
[Podman Desktop installation instructions](https://podman-desktop.io/docs/installation).
On macOS and Windows, complete the guided setup and allow Podman Desktop to
create and start a **Podman machine**. Also accept the option to install Compose
support. Leave Docker Desktop or Podman Desktop running while you use OSII.

### 3. Choose where your files live

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
Finder or File Explorer.

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

### 4. Start OSII

With Docker Desktop:

```bash
cd /path/to/osii
docker compose --profile chat --profile ocr up --build
```

With Podman Desktop:

```bash
cd /path/to/osii
podman compose --profile chat --profile ocr up --build
```

The first startup takes longer because the container images must be downloaded
and built. When the terminal output settles, open:

- **OSII dashboard:** <http://localhost:5173>
- **Backend status:** <http://localhost:8511/health>

In the dashboard, select **Processing** in the sidebar. Choose files from the
shared folder or use **Upload files**, select the operations you want, and
press **Start processing**. Progress and recent messages appear on the same
page.

Keep the terminal window open while using OSII. Stop everything with
<kbd>Ctrl</kbd>+<kbd>C</kbd>. To start it again later, run the same Compose
command.

### Troubleshooting startup

- If `podman compose` is unavailable, open Podman Desktop and install Compose
  from its setup or settings screen. Podman documents the same
  [`podman compose` workflow](https://podman-desktop.io/docs/compose/running-compose).
- If the browser cannot open OSII, verify that Docker Desktop or the Podman
  machine is running, then look for an error near the bottom of the terminal.
- If a corporate proxy blocks image downloads, ask an administrator to stage
  the required container images while connected. Once images and optional
  model weights are present, normal local use does not require internet access.

### Developer shortcuts

The Makefile uses Docker by default:

```bash
make dev
```

To use the same shortcuts with Podman:

```bash
make COMPOSE="podman compose" dev
```

To include the example subject-matter-expert processor:

```bash
make dev-examples
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
