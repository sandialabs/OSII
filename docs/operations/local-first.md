# Local and intermittently connected operation

OSII has a useful guaranteed baseline with no container runtime, network call,
credential, or model cache.

| Capability | Guaranteed baseline | Optional enhancement |
|---|---|---|
| Extraction | native text-layer formats; packaged baseline also includes full-page Tesseract OCR | Tika, OpenCV region OCR, domain processor |
| Synthesis | cited extractive Markdown preview | selected Ollama, OpenAI-compatible, or OpenAI-compatible chat model |
| Embedding | none required; lexical hashing remains an advanced compatibility method | selected OpenAI-compatible, Ollama, or OpenAI-compatible embedding model |
| Search | BM25 | provider/model-specific semantic FAISS index |
| Enrichment | statistics and keywords table | optional Toolbox wiki enrichers; domain Processor API service |
| Chat | grounded extractive answer | selected model provider |
| Browse/API/MCP | local dashboard, backend, and MCP | same contracts |

## Start OSII without containers

The normal path runs directly on macOS, Linux, or Windows. It creates and
updates its own `osii-env` environment; do not activate an environment first.
For a first look with bundled example files, use one command:

```bash
make demo
```

```powershell
.\scripts\osii.ps1 demo
```

For your own files already placed in `osii-data/source`, use:

```bash
make dev
```

```powershell
.\scripts\osii.ps1 dev
```

It starts the API (including grounded chat), worker, MCP, dashboard, five baseline processors, and
the lightweight provider bridge from editable source. The processors are the
Python text-layer PDF/Office extractor, ordinary full-page Tesseract OCR, the
no-AI cited source-excerpt preview, lexical token/word-pair hashing vectors,
and deterministic document statistics/frequent keywords. Bare-metal Tesseract
requires its native executable; the packaged baseline image contains it. The bridge makes no
generation request until that capability is used. Setup performs model
discovery and, when an embedding model is selected, validates one real vector
so a model that merely appears in `/models` is not incorrectly offered to
Intake.

This is the complete guaranteed baseline. It does not silently install or
launch optional system software. After the dashboard opens, use **Setup** to
connect Ollama or another AI endpoint or to start Apache Tika.

For the packaged Podman stack, `make run DISABLE_CONTAINER_PROXIES=true` or
`.\scripts\osii.ps1 run -DisableContainerProxies` starts in direct-network mode
while retaining the image's corporate certificate trust. The normal commands
inherit host proxy behavior. See [Corporate pilot images and Quay
releases](publishing-images.md#keep-corporate-certificates-but-disable-inherited-proxies)
for build commands and exact scope.

The host launcher starts the dashboard only after `http://127.0.0.1:8511/health`
responds. This is especially important on Windows, where several simultaneous
`uv run` processes can initialize more slowly. A backend failure therefore
produces a specific terminal error instead of a dashboard that repeatedly
reports Vite proxy failures.

On Windows, Ctrl+C terminates the complete child-process trees created by
Uvicorn reloaders, watchfiles, MCP, and npm/Vite. This prevents an apparently
stopped development stack from leaving ports 5173, 8022, 8080, 8085, 8092–8095, or
8511 occupied. The repository README includes a scoped recovery command for
processes left behind by older checkouts; it excludes Ollama and containerized
OCR services.

Host Python 3.12 dependencies live in the ignored `osii-env/` directory. OSII uses
that visible name because current macOS Python releases can skip editable
package path files beneath a hidden `.venv` directory.

Normal `make dev` reads model connections from the platform application-data
`profiles/development/deployment/models.toml` file. Add an OpenAI-compatible endpoint from **Setup**, or
use a separately installed Ollama service. **OSII does not install or launch
Ollama:** manage the separate application yourself when you use it, then open it or run `ollama serve`. In
**Setup → Model connections**, OSII queries `/api/tags` and shows
the installed models beside the endpoint configuration. The two approved US
starter models are:

- `all-minilm`, a roughly 46 MB Microsoft-origin embedding model.
- `llama3.2:1b`, a roughly 1.3 GB Meta chat and synthesis model.

Select **Download** to ask Ollama to pull a missing starter model and show its
progress. When the pull finishes, the card changes to **Installed**, OSII selects
and validates that model, and the Download action disappears. Existing documents
still need an **Additional processing → Build semantic embeddings** run from
Intake; installing a model does not silently reprocess the library. OSII bundles
no model weights. Downloads are limited to
`OSII_OLLAMA_ALLOWED_MODELS`; corporate administrators can extend that list
with other approved models.

The dashboard starter buttons deliberately cover only the small recommended
models. Use `ollama list` to inspect everything installed and `ollama pull
<model>` for other models permitted in your environment, then select **Check
connection & models** again.

BM25 is the automatic no-model retrieval fallback. Lexical hashing remains an
explicit vector-plumbing/shared-wording option and is never labeled semantic.

The equivalent manual command remains available, for example:

```bash
ollama pull all-minilm
```

Disable the Ollama provider in Setup to return chat, synthesis, and embedding
to their guaranteed local baselines. A configured OpenAI-compatible provider
replaces Ollama capability by capability, without changing the rest of OSII.

## Setup and local service control

Setup is organized around **Extractors, Synthesizers, Embedders, and
Enrichers**. These drawers start closed; open one at a time to inspect its full
inventory and descriptor-defined settings. Each closed header keeps the selected
method and availability count visible. **AI model connections** sit above the
drawers because one OpenAI-compatible or Ollama connection can supply both a
synthesizer and an embedder. Connecting AI is the normal setup path; bundled
model-free services are fallback capabilities when those services are unavailable.

Inside the **Extractors** drawer, **Extraction routing** assigns extension groups
to a primary extractor and ordered fallbacks. A worker tries the primary first and records
its failure before proceeding left-to-right through the fallbacks. Intake shows
only a compact readiness result and always uses the saved Setup routing.

Connection checks, service controls, route saves, and settings changes report
their results in a bottom-right notification that remains visible while the page
is scrolled. Success messages dismiss after eight seconds; errors remain until
dismissed or replaced by a later result. A notification also remains visible above
an open connection dialog. Detailed service output is still available through
**Advanced & diagnostics → Local capability services → Logs**.

The host launcher includes a loopback-only capability supervisor. The backend
uses a per-run private token to ask it for status or to start, stop, and restart
the extractor, preview synthesizer, compatibility embedder, enricher,
model-provider bridge, Apache Tika, and Tesseract OCR. The browser never sends
commands, paths, or executable names; it can invoke only those fixed service
IDs. Processes found on the expected ports but not started by the current OSII
launcher are shown as **Running externally** and are never stopped by OSII.

API, worker, dashboard, MCP, and chat remain owned by the top-level development
launcher because stopping the management plane from its own page would make
recovery confusing. Container deployments report capability health but disable
local lifecycle controls.

For host development, **Setup → AI model connections** can save an API key in the
platform application-data `profiles/development/deployment/secrets.env`. The file is plaintext and kept outside the repository; it
must not be copied or shared. Only the key's environment-variable name enters
`models.toml`; neither the key nor its name needs to enter `.osii`. The backend and model-provider bridge reread the file as needed.
Process environment values take precedence, and file writes are disabled in
container or administrator-managed deployments.

The normal `local.tesseract-page-ocr` processor runs each complete page through
Tesseract and is part of `osii-baseline-processors`. The separate
**Tesseract OCR with OpenCV regions** experiment lives in `osii-toolbox/`; see
[image publishing](publishing-images.md). Run and register it explicitly when
you need tunable contour detection and normalized region boxes for Source and
Split View overlays. Its default host port is 8081 so it can run beside the
baseline page OCR on port 8080.

On ordinary laptop-width screens, Split View places the source and grounded
text side by side and wraps each pane's controls within its own column. On
narrow screens, the panes stack so neither source content nor text is squeezed.

## Add and reprocess documents

The Intake page separates **Add files**, **Process library**, and **Activity**.
File-extension routing is intentionally not edited there; use **Setup →
Extraction routing** so the same policy applies consistently to every run.
Use Process library after installing a model to add embeddings or summaries to
documents that were extracted earlier. Use **Upgrade extraction** when a better
extractor becomes available; OSII preserves both extraction versions and lets
you decide whether the new result becomes primary. See
[Extraction versions and downstream lineage](../reference/extraction-versions.md).

Use the optional **Expert context** field for facts that are not reliably
inferable from the files themselves, such as experiment naming conventions,
control groups, units, or domain terminology. The context applies to every
document matched from the selected files or folders, appears in the final
review and Activity history, is saved in the intake manifest, and is passed to
extractors, synthesizers, and enrichers that support it.

Intake browses only within `OSII_SOURCE_DIR`. This boundary prevents a browser
session from walking the entire host filesystem. A mounted shared/network drive
works when `OSII_SOURCE_DIR` points to that mount and the OSII process can read
it. For a clearer read-only-source/local-artifact workflow, use `make
dev-shared SHARED_DRIVE_PATH="/mounted/share"` or `.\scripts\osii.ps1
dev-shared -SourceDir '\\server\share'`; see [Shared drives and
Samba](shared-drives.md). If folders are reorganized afterward, use **Document scope → Rescan source
paths**. OSII hashes current files, previews exact-content matches, and can
remap moved originals without re-running extraction; changed and new files are
left for a normal Intake run.

### Pause, resume, cancel, and inspect timing

Open **Intake → Activity** to control durable processing runs. **Pause** takes
effect after the file currently being processed, leaving completed documents
intact and freeing the single worker to claim another queued run. This makes it
safe to queue a small priority selection while a large batch is pausing.
**Resume** returns the paused run to the queue without repeating completed
files. **Cancel** is terminal and likewise takes effect after the current file;
it does not interrupt an extractor while that extractor is writing one
document.

Activity records start, finish, and processing duration for every attempted
file. Each run shows wall-clock elapsed time, measured processor time, average
time per completed file, and a simple remaining-time estimate. Expand **File
processing times** for fastest, slowest, and individual file durations. The
estimate is observational rather than a guarantee because file sizes and
selected processors can vary substantially.

Select **View log** on a run to show its complete, live-updating log in the
scrollable terminal panel at the bottom of Activity. A worker failure that
happens before the first file begins is reconciled from the durable queue into
an **error** run with the actual exception. Terminal runs no longer offer
pause, resume, or cancel actions.

The worker publishes a heartbeat while idle and while processing a long file.
If Windows terminates it, OSII marks the worker unavailable instead of silently
waiting. A replacement worker automatically returns interrupted work to the
queue after the abandoned lease expires; **Recover queue** performs the same
safe check on demand. A true error run offers **Retry failed run**, which resets
only failed items and preserves files that already completed.

## Generate an LLM wiki

LLM wiki generation is not implemented in Core. Start one or both optional
wiki enrichers from `osii-toolbox`, register their Processor API endpoints in
Setup, and assign a chat-model connection. Generate a wiki from a document,
folder, collection, or the whole library. The operation runs in the background,
records the processor and model provenance, and never substitutes the
extractive preview while labeling the result as an LLM wiki. See the
[LLM wiki walkthrough](../tutorials/llm-wiki.md).

Two additional dependency-free examples produce a frequency-ranked table of
lemmatized noun/adjective 2-, 3-, and 4-grams and a grounded list of named
entity candidates. Both use standard Processor API artifact formats; see
[Example keyword and entity enrichments](../tutorials/example-enrichments.md).

Model connections created in Setup use OSII's HTTP-only adapter for embeddings,
synthesis, and chat. Extraction remains local through native Python, Tika,
Tesseract, or a domain Processor API service. No provider-specific package is
installed; the adapter calls documented bearer-authenticated OpenAI-compatible
endpoints.

## Failure behavior

- Chat and synthesis follow the configured order and visibly report the
  provider actually used. Their final fallback is extractive.
- Embedding retries and resumes its own checkpoint. It never substitutes a
  different provider or model into an existing vector index.
- Semantic search falls back to BM25 when query embedding is unavailable.
- Scanned documents remain pending with an actionable Tesseract/OCR status when
  no OCR extractor is available.

Semantic indexes live under provider/model-specific directories and record
provider, model, digest when supplied, dimensions, normalization, chunking,
and creation time. Changing model or dimensions creates a different vector
space and requires a rebuild. Hashing is never labeled semantic.

The normal retrieval baseline uses sentence/paragraph-aligned windows of 768
characters with about 128 characters of overlap. Intake exposes the strategy,
size, and overlap. Both BM25 and vector search consume the same manifest, and
search carries page/segment provenance into document navigation. See
[retrieval chunking and overlap](../concepts/retrieval-chunking.md).

## Optional containers

Use `make build && make run` to test locally built images; corporate pilot hosts
set their approved image tag and use `make run` without a local build. See
[Corporate pilot images and Quay releases](publishing-images.md).
Ollama and the upstream OpenAI-compatible service remain separately managed endpoints.
OSII images contain only their lightweight HTTP adapters, not private packages
or model files.

To add Apache Tika while the editable stack runs, select **Start** beside
**Apache Tika** in Setup. OSII invokes its fixed Compose service and reports
the actual Podman/Docker failure when the runtime or image is unavailable. The
equivalent two-terminal workflow remains:

```bash
# Terminal 1
make dev

# Terminal 2
podman-compose --profile ocr up -d tika
```

The existing `TIKA_URL` configuration lets the running host services detect it
on port 9998.

When a Podman registry must be contacted without verifiable TLS certificates,
consult the registry administrator. OSII does not make insecure registry access
part of its normal launch workflow.

## Storage and disk diagnostics

Canonical text, manifests, provenance, synthesis, enrichments, and collection
membership remain inspectable `.osii` files. `.osii/state/catalog.sqlite3` is a
derived WAL-mode read catalog and may be deleted and rebuilt. Operational queue
state remains in `jobs.sqlite3`.

`make doctor` reports common
ignored disk consumers—including Python environments, `node_modules`, model
caches, OSII data, and Podman storage—and never deletes them.
