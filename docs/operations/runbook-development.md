# Start OSII from source

## Host-Python development

Use this workflow to run OSII from source. Install uv and Node.js 22.18 or
newer. macOS/Linux also need make; Windows uses PowerShell. uv obtains Python
3.12 and manages `osii-env/`. Install native Tesseract if you need scanned-PDF
or image OCR. Normal text extraction, keyword search, and the UI need no model
or container runtime.

## First start in a corporate checkout

Copy `.env.example` to `.env` before startup when corporate certificate trust
or other custom settings are required. Preserve an existing `.env`. Install uv,
Node.js, and make (macOS/Linux) using your approved software sources; uv can
obtain the required Python 3.12 itself. Never commit credentials or certificates.

```bash
# macOS/Linux — copy once, preserve existing settings
test -f .env || cp .env.example .env
# Configure corporate certificate trust in .env as described below, then:
make dev
```

```powershell
# Windows PowerShell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Configure corporate certificate trust in .env as described below, then:
.\scripts\osii.ps1 dev
```

Python selection on Windows is automatic: the launcher checks `py -3.12`,
then lets uv find or download Python 3.12. You do not need to locate python.exe
manually. If corporate policy requires a particular installation, use:

```powershell
.\scripts\osii.ps1 dev -PythonVersion "C:/path/to/Python312/python.exe"
```

A failed Python download and a failed package download both use uv's trust
settings below. Startup checks FastAPI and worker imports before opening
the dashboard. Processing workers use the same Python interpreter through
watchfiles function targets, including on Windows; they do not resolve a bare
`python` command from PATH. If an import check fails, retain the startup log,
correct any installation error, and rerun the normal startup command.

### Configure corporate certificate trust once

Both startup commands read certificate settings from root `.env` **before the
first uv invocation**, including when Python 3.12 is not installed.
System certificate trust defaults to enabled on both Windows and macOS, even
without an env file. OS-installed corporate roots apply to Python downloads
and package downloads. Set `UV_SYSTEM_CERTS=false` to opt out; explicit
settings, including the legacy `UV_NATIVE_TLS`, are respected.
One `.env` template works across platforms; separate `.env.windows` and
`.env.mac` files are unnecessary. An IT-approved Python installation remains
an option when corporate policy blocks downloads. These values are
inherited by dependency installation and child services. Existing shell/CI
variables override `.env`; editing `.env` does not override a value already set
in the terminal. PowerShell restores its prior certificate environment after
the command exits, so the next invocation rereads changed settings.

Named profiles work the same way: `make dev ENV_FILE=.env.corporate` or
`.\scripts\osii.ps1 dev -EnvFile .env.corporate` reads certificate settings
from that selected file before uv starts. An explicitly selected missing file
is reported immediately, without attempting a Python download.

If IT has installed and trusted the corporate CA in the operating system's
certificate store, put this in `.env`:

```dotenv
UV_SYSTEM_CERTS=true
```

Alternatively, obtain a **PEM-encoded CA bundle** from IT and keep it outside
the checkout. Set its actual absolute path in `.env`:

```dotenv
SSL_CERT_FILE="/absolute/path/to/corporate-ca-bundle.crt"
REQUESTS_CA_BUNDLE="/absolute/path/to/corporate-ca-bundle.crt"
NODE_EXTRA_CA_CERTS="/absolute/path/to/corporate-ca-bundle.crt"
```

On Windows, use a path such as `"C:/corporate certificates/ca-bundle.crt"`.
Quote paths with spaces. These early settings accept literal, single-line
`KEY=value` entries, optional single/double quotes, and `#` comments. Use the
full path in each entry; shell expressions, `${...}` expansion, and `~`
expansion are not supported. Configuration is read as data, never executed.

`SSL_CERT_FILE` configures uv; `REQUESTS_CA_BUNDLE` configures Python requests;
`NODE_EXTRA_CA_CERTS` configures Node/npm. The loader also supports `SSL_CERT_DIR`,
`PIP_CERT`, and the legacy uv option `UV_NATIVE_TLS`. `OSII_CA_BUNDLE` is not a uv
trust setting. Custom `SSL_CERT_FILE`/`SSL_CERT_DIR` settings replace uv's default
trust source, including system trust: remove stale overrides when choosing
`UV_SYSTEM_CERTS=true`. A `.crt` extension does not establish the encoding;
PEM contains `-----BEGIN CERTIFICATE-----`, while binary DER needs to be exported
as PEM. The bundle must contain the CA chain needed for your network.
See [uv certificate configuration](https://docs.astral.sh/uv/concepts/authentication/certificates/).

Then run the normal startup command above. Package installation still requires
access to approved Python/npm registries and, when Python is missing, the
configured Python download source. This configures trust without bypassing
certificate verification. Optional processors can also have their own endpoint
and credential settings; configure those when selecting them for processing.

If uv still reports `Invalid peer certificate: UnknownIssuer`, check for an old
shell override, the correct CA chain/PEM encoding, and the approved proxy or
download mirror with IT. An unreadable or non-PEM `SSL_CERT_FILE` is reported
before uv starts. Fix the setting and rerun; no environment deletion is needed.

The default document folder is `osii-data/source/`. Set `OSII_SOURCE_DIR` to
an existing readable folder to use your own files. Quote paths containing
spaces and use forward slashes on Windows. Connect shared drives in Finder or
Explorer first. OSII never mounts the share or stores share credentials.

Runtime data defaults to `osii-data/`, separately from original documents.
Configuration is in `osii-data/config/`. Preserve these directories and your
`.env` when updating the checkout.

Sidecars are the default library store. [Optional local PostgreSQL](../reference/local-storage.md)
uses the same startup commands, but requires explicit schema initialization and
an explicit, non-destructive import to carry over existing sidecar data.

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

## Start and check

Run `make dev` (Windows: `.\scripts\osii.ps1 dev`). This installs locked
Python dependencies and dashboard dependencies, then starts the application,
baseline processors, and enabled processor modules on the host. Module dependencies
are prepared once per project in that project's ignored `osii-env/`, separately
from Core. Later starts reuse those environments and npm dependencies.
Each Python service checks FastAPI and the Processor SDK in its own runtime
before starting. Operation-test diagnostics include that runtime’s executable,
package versions, and module paths. A passing Core import alone does not verify
a separately installed processor environment.

Modules include OpenCV/Tesseract (`8081`), CSV extraction (`8097`), collection
tables (`8098`), Readable Wiki (`8099`), Concept/Entity Wiki (`8100`), Banyan
(`8101`). Baseline full-page Tesseract remains on `8080`; native Tesseract
is still required for OCR. Nemotron and Wiki models require endpoint configuration.

Set individual `OSII_ENABLE_BANYAN=false` or the other
`OSII_ENABLE_…` switches in `.env` to omit a module's dependencies and startup.
Switch names are derived from each manifest service ID; see the
[manifest contract](../extending/processor-modules.md). Restart the stack after changing
these flags. Banyan's implementation and launch configuration are both under
`osii-processor-modules/banyan/`; no separate host project is needed.

Set `OSII_START_PROCESSOR_MODULES=false` in `.env` for baseline-only startup. The same
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
are verified only when processing begins. Network calls already in progress may outlive the browser timeout.

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
On Windows use `.\scripts\osii.ps1 dev -DryRun`.

## Update source

Stop with Ctrl+C, save your own work, update your checkout, and run `make dev`
again. No image build, installer, or package publication is needed. Back up
runtime data before product changes that require a storage migration.

## Connect an optional tool or your own processor

processor module implementations remain under `osii-processor-modules/` and start automatically
unless opted out as described above. To deploy a tool independently or connect
your own processor, start its service using its source instructions, register
its base URL in Setup's custom Processor API services, then choose its
extraction/enrichment route. The host workflow does not start containers.
The former Tika adapter and managed Java runtime are archived on
`archive/tika-2026-11-19`; `main` does not prepare or start them.

## Developer checks

Run `make test` and `make docs`. Windows developers can run the same underlying
uv and npm commands listed in the Makefile. Native Windows execution still
needs verification on a Windows workstation.


## Choose startup and intake defaults

`.env.example` is a short startup template. Processing preferences belong in
Setup, not in a list of per-processor environment variables. Copy it to an ignored
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

Use **Setup → Processing flows** to configure named reader/fallback chains,
synthesis, and enrichment. **Test sample** uses the definition page (physical
page 6) of the bundled text-layer NIST cloud-computing PDF and tiny text/model
requests. It records endpoint diagnostics and a configuration fingerprint. Results open immediately with numbered steps and
visible failures. Use **View errors** beside a flow to reopen its saved report,
even after refreshing, and **Copy report** for full diagnostics.
Changing the flow, models, or processor settings
invalidates its displayed test result; passing a sample is not a future
availability guarantee. Model-backed tests may use provider credits.

**Intake & Queue always starts with All processes**: extract, synthesize, enrich,
then embed. Select files and a flow, then queue. It does not ask users to rebuild
reader rules or repeat endpoint tests after file selection. Paths and selected
membership survive navigation to Setup in the same browser. The lightweight
selection preview reads metadata only. Flow-backed queue submissions defer
provider operation tests to the worker; errors remain retryable in the queue.
Legacy APIs retain explicit operation flags and saved preset compatibility.

Use a collection's **Processing status** panel to process existing text or reread
originals while preserving extraction history. Current semantic vectors depend
on the selected embedding model; this panel reports read, synthesis, enrichment,
and embedding coverage. Queue cards contain process information, files,
backends, errors, logs, and a copyable run report. Products are viewed on Files
and Collections, not embedded in queue cards.

Large-volume scanning is archived on `archive/large-volume-discovery-2026-11-19`.
The beta launcher does not start its worker. Inventory history remains intact.

Configuration ownership:

| Location | Purpose |
| --- | --- |
| Root `.env` | Bootstrap paths, corporate trust, Python, application ports, global startup switches; optional deployment overrides |
| Module `processor-module.toml` | Identity, command, default port, capabilities, offline request schema, startup schema/defaults |
| Setup → Model connections | Provider endpoints, model selection, replaceable credentials; saved in `models.toml` and private `secrets.env` |
| Setup → Processing defaults | Intake preferences, routing, bindings and processor settings; saved in `processors.toml` |
| Processor → Startup settings | Manifest-defined lifecycle options; restart the service after saving |

When `processors.toml` is absent, Core copies valid existing `tools.toml`
configuration atomically, then removes the migrated file. Existing `processors.toml`
always wins, even if invalid; parse errors are shown rather than falling back to
an older file. The `[tools]` registration table and legacy API/import names remain
compatible; only the filename changes. Routes, model bindings, request settings,
and unknown extension sections are retained. Legacy YAML/JSON import remains
supported. Avoid editing the old file after migration.

Existing private `.env` files are never rewritten. `OSII_INTAKE_PRESET`,
`OSII_INTAKE_CHUNK_SIZE`, `OSII_INTAKE_CHUNK_OVERLAP`,
`OSII_INTAKE_SYNTHESIZER`, and `OSII_INTAKE_ENRICHER` remain bootstrap defaults
until replaced in Setup (or `[intake]` in `processors.toml`). Saved Intake fields
win over those old values; an explicit run payload wins over both. Legacy
`OSII_INTAKE_INCLUDE_PATTERNS`, `OSII_INTAKE_EXCLUDE_PATTERNS`,
`OSII_INTAKE_INCLUDE_SUBFOLDERS`, and `OSII_INTAKE_SHOW_HIDDEN` remain in
`GET /api/intake/defaults` for API callers; the explicit discovery/browser controls
own file selection in the current UI.

### Advanced startup overrides

You can still add these to an existing private env file; omitting them uses the
application/manifest defaults. Module additions need no root-template edit.

| Optional overrides | Default / effect |
| --- | --- |
| `OSII_SOURCE_KIND` | `auto`; `shared` labels a mounted source |
| `OSII_ROOT`, `UPLOAD_ORIGINALS_ROOT`, `OSII_INVENTORY_DB` | Derived local runtime paths; keep inventory outside source roots |
| `OSII_STORAGE_BACKEND`, `DATABASE_URL` | Sidecars by default; PostgreSQL requires explicit initialization, never an automatic migration |
| `OSII_ACTIVE_PROFILE` | `development` |
| `OSII_DEFAULT_EXTRACTOR`, `OSII_DEFAULT_ENRICHER` | Native text and statistics/keywords fallback; prefer Setup's saved routing and method choices |
| `OSII_PROCESSOR_MODULES_DIR`, `OSII_PROCESSORS` | Trusted manifest root and additional Processor API URLs |
| `OSII_ENABLE_<SERVICE_ID>` | `true`; `false` omits preparation, registration and startup |
| Manifest `port_env` | Module's adapter port override; otherwise the manifest's `port` |
| `OSII_LOCAL_EXTRACTOR_PORT`, `OSII_TESSERACT_PORT` | `8092`, `8080` |
| `OSII_LOCAL_SYNTHESIZER_PORT`, `OSII_EMBEDDINGS_PORT`, `OSII_LOCAL_ENRICHER_PORT` | `8093`, `8085`, `8094` |

For module startup fields, explicit environment values win over saved Setup
choices, then manifest defaults. Setup shows the names of overriding variables
without revealing values. Restarting a module from Setup rereads its saved
startup settings. Global enable/port overrides require restarting `make dev`.

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
