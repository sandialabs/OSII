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

## Start and check

Run `make dev` (Windows: `.\\scripts\\osii.ps1 dev`). This installs locked
Python dependencies and dashboard dependencies, then starts the application
services on the host. Later starts reuse the environment and npm dependencies.

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

Optional processor implementations remain under `osii-toolbox/`; start their
Python service using that tool's source instructions. Register its base URL in
Setup's custom Processor API services, then choose its extraction/enrichment
route. The default host baseline starts automatically. External Tika can be
configured as an endpoint; the host workflow no longer starts containers.

## Verification

Run `make test` and `make docs`. Windows developers can run the same underlying
uv and npm commands listed in the Makefile. Native Windows execution still
needs verification on a Windows workstation.

Container builds, desktop installers, image catalogs, and publishing workflows
are preserved on `archive/workstation-deployment-2026-11-03`.
