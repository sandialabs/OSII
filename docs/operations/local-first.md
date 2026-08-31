# Local and intermittently connected operation

OSII has a useful guaranteed baseline with no container runtime, network call,
credential, or model cache.

| Capability | Guaranteed baseline | Optional enhancement |
|---|---|---|
| Extraction | native text-layer PDF, Office, RTF, and text/data formats | Tika, Tesseract OCR, domain processor |
| Synthesis | cited extractive Markdown preview | selected Ollama, OpenAI-compatible, or OpenAI-compatible chat model |
| Embedding | none required; lexical hashing remains an advanced compatibility method | selected OpenAI-compatible, Ollama, or OpenAI-compatible embedding model |
| Search | BM25 | provider/model-specific semantic FAISS index |
| Enrichment | statistics and keywords table | LLM wiki through the selected model-backed synthesizer; domain Processor API service |
| Chat | grounded extractive answer | selected model provider |
| Browse/API/MCP | local dashboard, backend, and MCP | same contracts |

## Host-native profiles

The normal development path is entirely bare metal:

```bash
make dev
```

```powershell
.\scripts\osii.ps1 dev
```

It starts the API (including grounded chat), worker, MCP, dashboard, four baseline processors, and
the lightweight provider bridge from editable source. The four processors are
the Python text-layer PDF/Office extractor, the no-AI cited source-excerpt
preview, lexical token/word-pair hashing vectors, and deterministic document
statistics/frequent keywords. The bridge makes no
generation or embedding request until that capability is used; Setup performs
only model discovery. Run applications without any processor or bridge using
`make dev-core`.

The host launcher starts the dashboard only after `http://127.0.0.1:8511/health`
responds. This is especially important on Windows, where several simultaneous
`uv run` processes can initialize more slowly. A backend failure therefore
produces a specific terminal error instead of a dashboard that repeatedly
reports Vite proxy failures.

On Windows, Ctrl+C terminates the complete child-process trees created by
Uvicorn reloaders, watchfiles, MCP, and npm/Vite. This prevents an apparently
stopped development stack from leaving ports 5173, 8022, 8085, 8092–8095, or
8511 occupied. The repository README includes a scoped recovery command for
processes left behind by older checkouts; it excludes Ollama and containerized
OCR services.

Host Python dependencies live in the ignored `osii-env/` directory. OSII uses
that visible name because current macOS Python releases can skip editable
package path files beneath a hidden `.venv` directory.

Normal `make dev` is Ollama-first when the separately installed Ollama service
is reachable. **OSII does not install or launch Ollama:** manage the separate
application yourself when you use it, then open it or run `ollama serve`. In
**Setup → Connect AI**, OSII queries `/api/tags` and shows
the installed models beside the endpoint configuration. The two approved US
starter models are:

- `all-minilm`, a roughly 46 MB Microsoft-origin embedding model.
- `llama3.2:1b`, a roughly 1.3 GB Meta chat and synthesis model.

Select **Download** to ask Ollama to pull a missing starter model and show its
progress. OSII bundles no model weights. Downloads are limited to
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

`make dev-ollama` and `.\scripts\osii.ps1 dev-ollama` remain explicit aliases
for this profile. Disable the Ollama provider in Setup to return chat,
synthesis, and embedding to their guaranteed local baselines. A higher-priority
enabled OpenAI-compatible provider replaces Ollama capability by
capability, without changing the rest of OSII.

On Windows, append `-DryRun` to any host profile command to validate its
service plan without opening ports, for example
`.\scripts\osii.ps1 dev-openai -DryRun`.

## Setup and local service control

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

For host development, **Setup → Connect AI** can save an API key in the
repository-root `.env`. The file is plaintext and excluded by `.gitignore`; it
must not be copied or shared. Only the key's environment-variable name enters
`.osii`. The backend and model-provider bridge reread the file as needed.
Process environment values take precedence, and file writes are disabled in
container or administrator-managed deployments.

The optional OpenCV/Tesseract OCR service can also run without a container.
The Tesseract executable is a separate manual installation and must already be
on `PATH`; verify that first with `tesseract --version`, then select **Start**
beside **Tesseract OCR** in Setup. The equivalent direct commands remain:

```bash
make dev-ocr-host
```

```powershell
.\scripts\osii.ps1 dev-ocr-host
```

The OSII wrapper listens on port 8080 and exposes its region-tuning interface at
`http://localhost:8080/demo`. OCR extraction stores normalized region boxes, which the Source and Split View
can overlay on the PDF.

On ordinary laptop-width screens, Split View places the source and grounded
text side by side and wraps each pane's controls within its own column. On
narrow screens, the panes stack so neither source content nor text is squeezed.

## Add and reprocess documents

The Intake page separates **Add files**, **Process library**, and **Activity**.
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
it. If folders are reorganized afterward, use **Document scope → Rescan source
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

## Generate an LLM wiki

With a model-backed synthesizer selected in Setup, OSII can compose that
capability into a standard wiki-Markdown enrichment. Generate a document wiki
from the document's **Wiki** tab or a collection wiki from the collection view.
The operation runs in the background, records the actual provider and model,
and never substitutes the extractive preview while labeling the result as an
LLM wiki. See the [LLM wiki walkthrough](../tutorials/llm-wiki.md).

Two additional dependency-free examples produce a frequency-ranked table of
lemmatized noun/adjective 2-, 3-, and 4-grams and a grounded list of named
entity candidates. Both use standard Processor API artifact formats; see
[Example keyword and entity enrichments](../tutorials/example-enrichments.md).

`make dev-openai` registers OSII's HTTP-only OpenAI-compatible adapter for
embeddings, synthesis, and chat. Extraction remains local through
native Python, Tika, Tesseract, or a domain Processor API service. The
corresponding Windows command is
`.\scripts\osii.ps1 dev-openai`. No provider-specific package is installed;
the adapter calls documented bearer-authenticated OpenAI-compatible endpoints.

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

Use `make dev-containers` when editable applications should use containerized
Tika and Tesseract. Use `make build && make run` to test locally built images;
corporate pilot hosts set their approved image tag and use `make run` without a
local build. See [Corporate pilot images and Quay releases](publishing-images.md).
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
make dev-tika
```

On Windows, the second command is `.\scripts\osii.ps1 dev-tika`. The existing
`TIKA_URL` configuration lets the running host services detect it on port 9998.

When a Podman registry must be contacted without verifiable TLS certificates,
use the explicit opt-in `make dev-containers-insecure`, or on Windows
`.\scripts\osii.ps1 dev-containers -InsecureRegistries`. This disables registry
TLS verification for image pulls/builds; it does not disable HTTPS checks for
OSII model or processor endpoints.

## Storage and disk diagnostics

Canonical text, manifests, provenance, synthesis, enrichments, and collection
membership remain inspectable `.osii` files. `.osii/state/catalog.sqlite3` is a
derived WAL-mode read catalog and may be deleted and rebuilt. Operational queue
state remains in `jobs.sqlite3`.

```bash
make catalog-verify
make catalog-rebuild
make doctor
```

The PowerShell script exposes the same command names. `doctor` reports common
ignored disk consumers—including Python environments, `node_modules`, model
caches, OSII data, and Podman storage—and never deletes them.
