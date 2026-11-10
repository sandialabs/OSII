# Start OSII from source

## Host-Python development

This is the supported path on `main` for now. Install uv and Node.js 22.18 or
newer. macOS/Linux also need make; Windows uses PowerShell. uv obtains Python
3.12 and manages `osii-env/`. Install native Tesseract if you need scanned-PDF
or image OCR. Normal text extraction, keyword search, and the UI need no model
or container runtime.

## First start in a corporate checkout

Copy `.env.example` to `.env` only if you want to customize defaults. Never
commit credentials. Package installation still requires access to your approved
Python and npm registries and their corporate trust configuration.

```bash
# macOS/Linux — copy once, preserve existing settings
test -f .env || cp .env.example .env
make dev
```

```powershell
# Windows PowerShell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\\scripts\\osii.ps1 dev
```

The default document folder is `osii-data/source/`. Set `OSII_SOURCE_DIR` to
an existing readable folder to use your own files. Quote paths containing
spaces and use forward slashes on Windows. Connect shared drives in Finder or
Explorer first. OSII never mounts the share or stores share credentials.

Runtime data defaults to `osii-data/`, separately from original documents.
Configuration is in `osii-data/config/`. Preserve these directories and your
`.env` when updating the checkout.

For the shared model endpoint set `OPENAI_BASE_URL`, `OSII_CHAT_MODEL`, and
`OSII_EMBEDDING_MODEL` if embeddings are available. Enter credentials in
Setup or inject `OPENAI_API_KEY`. Existing saved model settings are retained;
change them in Setup rather than expecting new defaults to overwrite them.

Setup keeps all six readiness steps numbered, including completed steps. Model
connections show an endpoint status from automatic model-list checks, refreshed
every minute while open. These do not run inference. Hover or focus the status
for check details. **Test models** checks selected-model availability and makes
an embedding request when configured. Review **Processing defaults** below the
connections, then use **Continue to Intake** at the bottom of Setup.

## Work on local and server together

OSII-local has no user accounts or login screen. Its normal `make dev` startup
includes **File inventory** for coarse metadata discovery, alongside existing
Intake, Files, Search, Topics, and Chat. Scan metadata first when deciding what
to process; scans do not read file contents, hash documents, or invoke models.
See [file inventory](large-volumes.md) for filters, resumable scans, selection
budgets, and local-disk database recovery. Hosted user authentication belongs
only to OSII-server. Model-provider credentials and private inter-process
tokens do not represent OSII-local user accounts.

Keep each chat and terminal in its own existing worktree:

| Application | Checkout | Branch | API / dashboard | Python environment |
| --- | --- | --- | --- | --- |
| OSII-local | `/Users/heidi/Projects/OSII/osii-local` | `main` | `8511` / `5173` | `osii-env/` |
| OSII-server | `/Users/heidi/Projects/OSII/osii-server` | `osii-server` | `8512` / `5174` | `.venv/` |

Each checkout owns its `.env`, configuration, dependencies, and runtime data.
Local's baseline extractor uses `8092`; server's uses `8192`. Use checkout-local
settings rather than exporting OSII paths or ports globally across terminals.
Keep local filesystem storage separate from the server's PostgreSQL database.
Preserve in-progress work in each worktree; branch switching is unnecessary.
Transfer portable fixes in focused commits only after committing is authorized,
review and test each cherry-pick, and avoid whole-branch merges between products.

## Use shared source documents

Mount the share through the operating system, then set these values in the
local checkout's `.env` (adapt the source path for your machine):

```dotenv
OSII_SOURCE_DIR=/Volumes/home/hk
OSII_SOURCE_KIND=shared
OSII_RUNTIME_DIR=./osii-data/nas-hk
OSII_CONFIG_DIR=./osii-data/config
```

Run the same `make dev` or PowerShell command. Originals are read in place;
the `.osii` store, catalog, jobs, indexes, and uploads stay on the workstation.
The explicit config path retains existing Setup settings when changing the
runtime directory. Existing data in other runtime directories is retained.
Do not put `OSII_RUNTIME_DIR` or `OSII_ROOT` on the share: the catalog uses
[SQLite WAL, which does not support network filesystems](https://sqlite.org/wal.html).
This configuration supports one local instance; simultaneous instances sharing
a writable store have not been verified.

Repeat the isolated PDF ingest/search/restart check from the local checkout:

```bash
OSII_TEST_SHARED_DIR=/Volumes/home/hk UV_PROJECT_ENVIRONMENT="$PWD/osii-env" uv run --frozen --python 3.12 --package osii --extra dev python -m pytest osii-core/tests/test_source_access.py -q
```

```powershell
$env:OSII_TEST_SHARED_DIR = '//server/share/documents'
$env:UV_PROJECT_ENVIRONMENT = "$PWD/osii-env"
uv run --frozen --python 3.12 --package osii --extra dev python -m pytest osii-core/tests/test_source_access.py -q
```

The test creates and removes only its own temporary corpus on the share, uses
temporary local state and available ports, and restarts API, worker, and text
extractor processes. It checks original hashes, extracted text, search results,
persisted runs, and SQLite integrity. It simulates loss of the source path by
renaming its test folder and restoring it; it never unmounts the user's share.
Permission failures and interrupted scans are injected in separate regression
tests. A failed rescan must return an error without marking documents missing.

On November 4, 2026, this check passed against the NAS at `192.168.1.150`,
mounted at `/Volumes/home` over SMB 3.1.1, using `/Volumes/home/hk` for the test
corpus. Actual network interruption, NAS ACL enforcement, concurrent OSII
instances, Windows execution, and a large PDF corpus remain unverified.

## Start and check

Run `make dev` (Windows: `.\\scripts\\osii.ps1 dev`). This installs locked
Python dependencies and dashboard dependencies, then starts the application,
baseline processors, and all Toolbox services on the host. Toolbox dependencies
are prepared once per project in that project's ignored `osii-env/`, separately
from Core. Later starts reuse those environments and npm dependencies.

The Toolbox services are OpenCV/Tesseract region OCR (`8081`), CSV extraction
(`8097`), collection-table enrichment (`8098`), Readable LLM Wiki (`8099`), and
Concept and Entity LLM Wiki (`8100`). `.env.example` lists their port overrides.
Baseline full-page Tesseract remains on `8080`. Install native Tesseract for
either OCR service. All five Toolbox endpoints are registered with Core, and
their health checks must pass before the dashboard starts.

Set `OSII_START_TOOLBOX=false` in `.env` for baseline-only startup. The same
setting works with `make dev`, `make demo`, and the PowerShell commands.
Setup's service controls can start stopped tools on demand. Starting services
does not change saved processing routes, invoke models, or download model
weights. Select a tool and run processing explicitly; wiki enrichment requires
a configured chat connection. Ctrl+C stops all services owned by the launcher.

Open `http://localhost:5173` and check `http://localhost:8511/health`.
In Intake process one small text file, then search for its text. The API must
be healthy before the dashboard starts. Keep the terminal open and stop with
Ctrl+C. Logs are printed in that terminal with service names.

Use `make demo` (Windows: `.\\scripts\\osii.ps1 demo`) to install the small
example corpus and start the same application. Demo setup requires download
access; plain `make dev` does not download the demo corpus.

## If file selection takes too long

If Intake remains on **Updating file selection**, quick preview should only
enumerate metadata, not hash PDF contents. The client stops waiting after 30
seconds with Retry and File inventory options. Choose a narrower folder or use
**File inventory** for resumable discovery. Processing counts in quick preview
are estimates from saved catalog identities; content hashes and deduplication
are verified only when processing begins. Network calls already in progress
may outlive the browser timeout. See the [shared-drive workflow plan](../planning/shared-drive-intake.md)
for the proposed background discovery/staging integration for very large shares.

## If startup fails

- Confirm `uv --version`, `node --version`, and `npm --version` work.
- Read the first service error in the launch terminal. Correct corporate proxy,
  certificate, or registry configuration before retrying installation.
- If a port is occupied, stop the OSII terminal that owns it; do not start a
  second copy against the same runtime data. Default ports are documented in
  `.env.example`.
- If a configured source folder is unavailable, reconnect it before retrying.
- Without native Tesseract, use text-layer documents or install it for OCR.

Preview the process plan without launching services:
`uv run --no-project --python 3.12 python scripts/dev_stack.py --dry-run`.
On Windows use `.\\scripts\\osii.ps1 dev -DryRun`.

## Update source

Stop with Ctrl+C, save your own work, update your checkout, and run `make dev`
again. No image build, installer, or package publication is needed. Back up
runtime data before product changes that require a storage migration.

## Connect an optional tool or your own processor

Toolbox implementations remain under `osii-toolbox/` and start automatically
unless opted out as described above. To deploy a tool independently or connect
your own processor, start its service using its source instructions, register
its base URL in Setup's custom Processor API services, then choose its
extraction/enrichment route. External Tika can be
configured as an endpoint; the host workflow no longer starts containers.

## Verification

Run `make test` and `make docs`. Windows developers can run the same underlying
uv and npm commands listed in the Makefile. Native Windows execution still
needs verification on a Windows workstation.

Container builds, desktop installers, image catalogs, and publishing workflows
are preserved on `archive/workstation-deployment-2026-11-03`.

## Standalone shared RAG experiments

For extension contracts and custom reranking, see the
[RAG strategy authoring guide](../extending/rag-strategies.md).

Normal local startup now installs the locked `rag-haystack` extra for Chat's
opt-in experiment controls. Restart `make dev` (Windows: `.\\scripts\\osii.ps1 dev`)
after updating. The extra remains optional for standalone Python users and is
not part of the baseline hosted image.

In local **Chat**, keep **Configured chat** for existing behavior, or select
**Keyword baseline**, **Hybrid baseline**, **Hybrid + reranker**, or
**Iterative hybrid** before sending a question. Reranking requires a configured
[Core endpoint](model-endpoints.md); iterative planning requires a selected
chat model in Setup. Unavailable choices explain what is missing.

For comparisons, choose a scope/collection, enter one question, select two or
three profile chips, and click **Compare selected modes**. The same question,
scope, history, and captured chat settings feed each mode. Inspect evidence and
steps, actual retrieval fallback, call counts, timing, and available chat token
usage; download the comparison JSON to retain results. Comparisons can make
multiple model calls and incur their normal charges. Query-embedding/reranker
token costs are not included in the displayed chat usage.

Process documents in Intake first; selecting a profile does not re-extract or
re-embed them. Ordinary search may initialize its derived keyword cache. Hybrid
reports when it uses keyword fallback instead of vector results. Avoid changing
models, collection membership, or processing while comparing: observed changes
abort the comparison. The filesystem read guard is not a transactional snapshot.
Switching profile or scope clears the displayed conversation to avoid mixing
results. Experiments are local-first; hosted Chat activation needs its own
PostgreSQL/authenticated adapter.

The synthetic CLI demo below uses two small in-memory excerpts and deterministic
decisions; it makes no network/model calls and is not evidence of real-corpus
answer quality. Run it from the repository root:

```bash
uv run --package osii --extra rag-haystack python -m osii.rag.strategies --demo
uv run --package osii --extra rag-haystack python -m osii.rag.strategies --demo --strategy single-pass
uv run --package osii --extra rag-haystack --extra dev python -m pytest osii-core/rag-tests -q
```

The iterative demo finds the missing isotope table on a second search and cites
it. The single-pass demo abstains because that evidence was not yet retrieved.
The JSON output includes evidence/provenance, steps, model usage, and stop reason.

The HTTP client below targets standalone/server `/api/search`. Volume mode
(`/api/volume/search`) needs a separate scope-preserving adapter; use the offline
demo or explicit Python callbacks there for now.

For an existing collection, use its Core collection ID and an explicit endpoint
and model. Hosted Core uses the normal username/password login; the password is
prompted invisibly. Omit `--username` for a local Core without hosted authentication.
Store the model key in an ignored configuration file using
`OSII_RAG_MODEL_API_KEY_FILE` (path to a private key file) or
`OSII_RAG_MODEL_API_KEY`. Keys are never command-line arguments. The Core and model
sessions are separate; OSII credentials are not sent to the model endpoint.

```bash
uv run --env-file .env --package osii --extra rag-haystack python -m osii.rag.strategies \
  "What evidence supports this finding?" \
  --api-url https://osii.app --username heidikmkv \
  --scope collection --scope-id COLLECTION_ID \
  --mode lexical --strategy iterative \
  --chat-url https://openrouter.ai/api/v1 \
  --chat-model google/gemma-4-31b-it:free --allow-model-calls
```

Replace the example with the exact corporate Gemma model ID and endpoint when
available, or explicitly choose `openai/gpt-4.1-mini` for the metered comparison.
Free-provider quotas/availability still apply. No paid provider is selected as
an automatic fallback. `--allow-model-calls` acknowledges external requests and
possible charges. `--mode hybrid` or `semantic` also invokes the deployment's
selected query embedder; the experiment does not change that configuration.

Defaults are three retrievals, three model decisions, six hits per retrieval,
18 retained excerpts, 24,000 evidence-text characters, 900 output tokens per
call, and a 90-second cooperative deadline. Customize limits in Python or use
`--max-retrievals` / `--max-model-calls`. Adapter HTTP timeouts are separate from
that cooperative deadline. Keep traces outside Git; they contain retrieved text.

Python developers can supply ordinary callables instead of running any API:

```python
from osii.rag.strategies import Decision, Evidence, Question, Scope
from osii.rag.strategies.haystack import run

# Bind retrieval to the authorized collection/snapshot in your adapter.
def retrieve(query: str, *, top_k: int):
    return [Evidence("chunk-1", "file-1", "The source uses 241Am.",
                     source_relpath="report.pdf", representation="text-layer:v1")]

def decide(context):
    return Decision("answer", answer=context.evidence[0].text,
                    citation_ids=(context.evidence[0].id,))

result = run(Question("Which source?", Scope("collection", "collection-1")),
             retrieve=retrieve, decide=decide)
assert result.citations[0].file_id == "file-1"
```

The callback in this small example is deterministic, not a model. A real storage
adapter enforces scope and snapshot semantics before returning evidence; the
strategy cannot authenticate an arbitrary developer-supplied callable. Supply
`ChatDecider` or your own decision function to run model-backed experiments.
Importing the contracts alone loads no store, web server, or Haystack framework.

## Choose startup and intake defaults

`.env.example` documents the complete host configuration. Copy it to an ignored
`.env` once, or keep several private files and select one at startup:

```bash
make dev ENV_FILE=.env.personal
```

```powershell
.\scripts\osii.ps1 dev -EnvFile .env.personal
```

The process environment wins over the selected file. Restart the launcher after
changing environment settings. Paths are checkout-relative; values are literal,
without shell variable interpolation. This selects a configuration file, not a
user account. OSII-local has no login.

Set `OSII_INTAKE_PRESET` to `text`, `search`, `summary-search`, or `full`.
Intake displays the preset prominently and lets you switch for each batch, then
adjust individual steps. These presets initialize the form, never start work.
`text` needs no model; `search` adds semantic embeddings; `summary-search` adds
summaries; `full` also enables the selected enrichment. Explicit API run payloads
remain authoritative. Patterns, subfolders, hidden files, chunk sizes, and method
overrides have documented `OSII_INTAKE_*` settings in the example file. The
processor and model must be available before model-backed work can run.

For an OpenRouter or corporate OpenAI-compatible provider, set its API base URL,
exact chat and embedding model IDs, and credentials. Shared `OPENAI_BASE_URL`
and `OPENAI_API_KEY` are the simplest arrangement. Independent
`OSII_CHAT_BASE_URL` / `OSII_EMBEDDING_BASE_URL` use only their own capability's
key or key file; they deliberately never inherit the shared key. Use only one credential source per capability; leave an inline key blank when
using its key file. Use Setup's connection test before starting a paid intake.

Model environment values seed **new** `models.toml` files. Existing saved
selections are preserved. Use a separate `OSII_CONFIG_DIR` for each provider
profile, or change existing selections in Setup. `OSII_RUNTIME_DIR` controls the
library independently: switching provider configuration does not require moving
or deleting your documents. Changing embedding models requires rebuilding the
semantic index; vectors from different models must not be combined.

Private environment templates such as `.env.example.openrouter` are ignored by
Git and are not distributed with the repository. If you maintain one locally,
launch it with `make dev ENV_FILE=.env.example.openrouter`. For corporate transfer,
replace URLs, model IDs, credential locations, and source/runtime paths; keep
runtime databases on local disk. Do not copy provider secrets into committed files.

## Library overview and file metadata search

**Library at a glance** is a left-menu tool with format, date, processing, and
topic summaries. It is separate from the home **Files** grid. Use **Search metadata**
in Files to open the drawer and combine filename/path words, file format, size,
modification date, extracted-text availability, summaries, and enrichments.
Filters apply to recorded metadata for the files in the local library; they do
not read original contents or call a model. Missing size/date metadata is excluded
only when that field is constrained. Modification-date filters include both
boundary days in UTC. Clear filters to restore the complete Files grid.

For names and sizes of source files that have not been ingested, use **File
inventory** and its metadata scan. Content and semantic retrieval remain in
**Search**.

## Durable processing APIs

Standalone document synthesis (`POST /api/synthesis/objects/{file_id}`), collection
synthesis (`POST /api/collections/{collection_id}/syntheses`), and full-index builds
(`POST /api/embeddings/build`) all queue work for the normal local worker started
by `make dev`. Their existing request fields and response identifiers remain
available. Synthesis returns a `run_id` and an initial `queued` status. Use
Activity or `/api/runs/{run_id}` for status, logs, pause, resume, cancel, and retry.

Embedding build requests retain `job_id: "segments"` and the legacy in-progress
`status: "running"`. The additive `queue_status` exposes the actual queued state,
and `run_id` identifies this specific build. `GET /api/embeddings/build/segments`
tracks the most recently submitted full build, including after API restart.
`GET /api/embeddings/build/{run_id}` provides stable polling when builds overlap.
Unknown embedding job IDs retain the existing JSON error response.

A worker killed mid-build resumes from committed vectors. Failed documents are
reported in the run's `indexing_progress.failures`; healthy documents continue
and their vectors are retained. Retry the same run after fixing a transient
failure. A full rebuild keeps the previous index published until all selected
members succeed; it then replaces that provider/model's full snapshot. New files
added after submission belong in another build. Text changed before retry is
rechunked, with matching successful chunks reused. Models, endpoints, and method
versions cannot silently change within a run; start another run for a changed
configuration. Pause and cancel are cooperative between provider requests.

Synthesis saves its input text and expert context before queueing. Its completed
result checkpoint prevents regeneration after a restart or lost queue completion
acknowledgement. A process lost after a provider response but before persistence
can still repeat that response; provider requests are at least once.

Environment templates expose current endpoint/model names and Intake settings.
Use `OSII_CHAT_MODEL` and `OSII_EMBEDDING_MODEL`; saved choices in Setup remain
authoritative. Obsolete shared-endpoint aliases and separate `CHAT_PROVIDER*`
routing flags are omitted from the templates. Older external configurations can
still be read, but normal startup no longer injects overrides of saved chat defaults.
