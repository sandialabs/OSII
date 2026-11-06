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

For the shared model endpoint set `OPENAI_BASE_URL`, `OPENAI_CHAT_MODEL`, and
`OPENAI_EMBEDDING_MODEL` if embeddings are available. Enter credentials in
Setup or inject `OPENAI_API_KEY`. Existing saved model settings are retained;
change them in Setup rather than expecting new defaults to overwrite them.

## Work on local and server together

Keep each chat and terminal in its own existing worktree:

| Application | Checkout | Branch | API / dashboard | Python environment |
| --- | --- | --- | --- | --- |
| OSII-local | `/Users/heidi/Projects/OSII/osii` | `main` | `8511` / `5173` | `osii-env/` |
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

Install the optional Haystack extra from the repository root. It is not needed
by normal startup and is not part of the baseline server image. The synthetic
demo uses two small in-memory excerpts and deterministic decisions; it makes no
network/model calls and is not evidence of real-corpus answer quality.

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
