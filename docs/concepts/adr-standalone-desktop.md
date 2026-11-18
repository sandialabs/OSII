# Standalone desktop delivery

## Decision

Maintain `osii-standalone` as a Windows 11 x64 delivery branch. Ship the existing
React dashboard in Electron with a PyInstaller one-folder Python runtime and
bundled Tesseract. Prepare dependencies on the build machine. An installed
application neither resolves packages nor invokes uv, npm, Java or a container
engine. There are no image catalogs, Quay logins or component update services.

Electron supplies a consistent browser and avoids a Rust build toolchain.
Its larger runtime and security-update responsibility are accepted. Tauri can
also bundle Python, but adds Rust and WebView2 distribution. An ordinary-browser
launcher saves space but complicates lifecycle ownership and browser testing.
None of these shells removes Python packaging work; the frozen-runtime gate
therefore precedes installer validation.

## Ownership and interfaces

- Electron owns the window, single-instance lock, native folder chooser and
  application exit. Its renderer is sandboxed, has no Node integration, and
  cannot invoke desktop operations from dashboard or document content.
- The Python supervisor receives fixed commands over private inherited pipes.
  It owns the API, processing worker, inventory worker, six baseline services
  and service-management HTTP endpoint. It does not spawn developer tools.
- Each HTTP socket is bound to an available loopback port before launch and
  transferred to its child. Windows uses socket sharing, not bind/close/rebind.
  Runtime addresses enter process configuration, not saved model settings.
- The existing Core API serves compiled dashboard assets and SPA routes.
  A per-launch bearer token, exact Host/Origin checks and loopback binding
  protect the desktop session. The Electron session supplies its token only
  to that backend. This is private process access, not user authentication.
- Windows Job Objects own the supervisor and each role's descendants. Pipe
  closure requests shutdown; process termination also kills OCR and scanner
  grandchildren. Existing durable queues remain responsible for recovery.
- Core APIs, Processor API v1 identities and `.osii` formats remain compatible.
  Baseline services have unique Python package names so their modules cannot
  shadow one another inside a frozen runtime. Volume runtime discovery supplies
  its processor URLs instead of hard-coded development ports.

## Data and capability boundaries

Originals remain separate from writable library state and can reside on an
already-connected mapped drive or UNC share. Canonical sidecars and SQLite
state stay on local disk. The inventory remains canonical and independent of
rebuildable catalogs. Explicit existing-library selection checks schema and
ownership without resetting evidence or importing a checkout's `.env`.
New profiles start without model connections. Existing settings are reused only
when their configuration directory is explicitly selected.

The library lock is held by the launcher until its children stop. Both this
branch's source launcher and desktop supervisor use it. Older source checkouts
without that protocol must be stopped manually; do not claim that an old binary
will honor a lock it does not implement. Schema changes require their own
explicit migration and backup workflow, not an installer upgrade.

| Included offline | Optional connections | Excluded runtimes |
| --- | --- | --- |
| PDF/Office/text extraction, full-page OCR, metadata inventory, keyword search, extractive previews/chat, statistics, shared editing/reports/exports | Ollama, OpenAI-compatible models, external Processor API services, MCP clients through separately configured integration | PostgreSQL, Java/Tika, Banyan, OpenCV region OCR, specialist dataset processors, Haystack, model weights |

Semantic search and AI features preserve their existing model requirements.
Dataset text extraction does not imply specialist dataset-analysis parity.
Topic Explorer and research workflows retain their existing capability and
experimental labels.

## Release and maintenance

Use one product version and locked build inputs. The full NSIS installer runs
per-user without elevation and preserves application data on uninstall.
Updates replace the whole stopped application; no background updater is added.
Native Windows CI tests frozen libraries, real model HTTP calls, the Electron
window and installer lifecycle. A clean standard-user Windows 11 acceptance
run and valid signing credentials are additional broad-release requirements.

Transfer shared fixes as focused reviewed commits. Do not merge the archived
container launcher or hosted persistence into this branch.

See [installation, building and acceptance](../operations/standalone.md).
