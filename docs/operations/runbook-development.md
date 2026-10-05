# Development runbooks

Choose one path: source development, local container builds, or pulling a
published release. The last path needs no compiler, Python environment, or
source checkout. The [desktop launcher](runbook-desktop.md) is the normal
non-developer route.

## Host-Python development

**When:** Edit OSII Core, processors, or the dashboard without building OSII
containers. This is the “bare metal” path, not a second production installer.

**Before:** Install `uv` and Node.js 22. The commands request Python 3.12 and
manage `osii-env`; do not activate another virtual environment. For native OCR,
install the Tesseract program on the host.

### First start in a corporate checkout

For developers, **yes: copy `.env.example` to `.env` once and edit it before
starting OSII**. The filename is `.env`, not `.end`. This is workstation
configuration, not a release/build step. A public demo can run without it;
installed launcher users do not need a repository `.env`.

From the repository root, create the file only if it is missing:

```bash
# macOS/Linux
test -f .env || cp .env.example .env
```

```powershell
# Windows PowerShell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Open `.env` in a text editor and review just the settings you need:

- **Your documents:** set `OSII_SOURCE_DIR` to an existing readable folder.
  Quote paths with spaces; on Windows use forward slashes, for example
  `OSII_SOURCE_DIR="C:/Users/Heidi/My Documents"`.
- **Your model endpoint, if wanted:** for an approved OpenAI-compatible service,
  set `OPENAI_BASE_URL` to its supplied API base address (usually ending
  in `/v1`) and `OPENAI_CHAT_MODEL` to its exact model ID. Set
  `OPENAI_EMBEDDING_MODEL` only if the service provides embeddings. Leave
  `OPENAI_API_KEY` blank to enter the key later through **Setup → Add LLM**;
  a nonempty startup key takes precedence over keys entered in Setup.
- **Your custom processors, if wanted:** `OSII_PROCESSORS` accepts
  comma-separated OSII Processor API base URLs. These are not LLM URLs. See
  [Connect an optional tool or your own processor](#connect-an-optional-tool-or-your-own-processor).

Keep the other defaults unless your deployment requires a change. Ensure
IT-approved package mirrors, certificate trust, and proxy settings are in place
before the first dependency installation. Never commit `.env` or API keys.

Start with `make dev` or `.\scripts\osii.ps1 dev` below; no virtual-environment
activation or container build is needed. After editing `.env`, stop with Ctrl+C
and start again. **Copy once, edit as needed—not on every start or update.**
Shell variables can override `.env`. Existing model choices in
`osii-data/config/models.toml` remain saved; change those through Setup instead
of expecting a new `.env` to replace them.

### Start and check

**Do:** From the repository root, start with your own files and keep the
terminal open:

```bash
# macOS/Linux
make dev
```

```powershell
# Windows PowerShell
.\scripts\osii.ps1 dev
```

For a public introduction with example files, use `make demo` or
`.\scripts\osii.ps1 demo` instead.

**Check:** Open `http://localhost:5173` and `http://localhost:8511/health`.
Process one small file in Intake. Stop with Ctrl+C in the launch terminal.

**If it fails:** Run the environment checks in [local-first operation](local-first.md).
Host Ollama uses `http://127.0.0.1:11434`; that address is *not* right from
inside a container.

**Update source:** stop with Ctrl+C, save/commit your own work, then
`git pull --ff-only` on your development branch and repeat `make dev` (or
`.\scripts\osii.ps1 dev`). The launch script refreshes its managed dependencies;
you do not rebuild images or publish a package to test local Python changes.
Use the [first-start checklist](#first-start-in-a-corporate-checkout) for host
configuration; `.env.containers.example` is for the separate container path.
Host launch profiles prefer a configured OpenAI-compatible endpoint,
otherwise Ollama; choose/test processing methods in Setup. A running host
Ollama must have the models selected in that profile. For reproducible use of
a released source version, use a clean checkout of its `vX.Y.Z` tag instead of
pulling an unrelated branch. See the release's Python-package version before
installing `osii` into a separate notebook environment.

### Connect an optional tool or your own processor

**Start it → register its address → choose when OSII uses it.** OSII connects
to configured addresses; it does not scan `osii-toolbox/` for services.
`make dev` starts and supplies the baseline service addresses automatically.
Optional tools are not all started by default.

1. **Start only the tool you need.** For a published Toolbox image, leave
   `make dev` running and use a second terminal:

   ```bash
   make toolbox-run TOOL=tabular
   ```

   ```powershell
   .\scripts\osii.ps1 toolbox-run -Tool tabular
   ```

   This needs Podman, its Compose provider, and the approved image prefix/tag
   configured in `.env`; it pulls a missing image but does not build one.
   See [optional Toolbox images](publishing-images.md#publish-and-run-optional-toolbox-images).
   For your own processor, start its service using its own instructions instead.
2. **Register the running service.** In **Setup → Advanced & diagnostics →
   Custom Processor API services**, paste its base URL, for example
   `http://127.0.0.1:8097`, and select **Discover and register**. Do not append
   `/v1/extract`. OSII reads `/v1/descriptor` to learn its name, kind, settings,
   and model requirements. Choose a model connection only when required.
3. **Choose when to use it.** For an extractor, open **Extractors → Extraction
   routing**, choose it for the relevant file types, and **Save routes**. Test
   one file in Intake. Registration alone does not replace existing routes.

The registration is saved in the active `tools.toml`, normally
`osii-data/config/tools.toml`, and survives restarts. Registration does not
start the service: it must still be running when OSII calls it. A multi-service
tool, such as Tabular, has separate extractor and enricher URLs; register each
capability you want to use.

For startup-configured discovery instead of UI registration, put a service base
URL in root `.env`, for example `OSII_PROCESSORS=http://127.0.0.1:8097`, and
restart `make dev`. Append additional URLs with commas. This also does not
start the service or select extraction routes. These host addresses are for
bare-metal Core; containerized Core needs a reachable container-network or
host address, not its own `127.0.0.1`.

The currently supported commands are `make dev` and a separate
`make toolbox-run TOOL=...`. `make dev toolbox` and `make dev TOOLBOX=...` are
not implemented startup options.

## Direct Compose development

**When:** Test the packaged Linux images locally without the desktop launcher.

**Before:** Start Podman and its Compose provider. Copy
`.env.containers.example` to `.env` once and review source and image settings;
never commit `.env`. On Apple Silicon the native container architecture is
`linux/arm64`; on an Intel/AMD computer it is `linux/amd64`.

**Do:** From the repository root:

```bash
# macOS/Linux
make build
make run
```

```powershell
# Windows PowerShell
.\scripts\osii.ps1 build
.\scripts\osii.ps1 run
```

**Check:** Open `http://localhost:5173`. Compare `podman info --format
'{{.Host.Arch}}'` with `podman images --format
'{{.Repository}}:{{.Tag}} {{.Arch}}'` if Podman reports an architecture
mismatch. Use `podman ps --format '{{.Names}} {{.Ports}}'` to identify port
owners before stopping anything.

**If it fails:** `make down` (or `.\scripts\osii.ps1 down`) stops only this
repository's Compose project, not launcher-created projects. Check the exact
project owner with `podman ps`. Containerized Ollama connections use
`http://host.containers.internal:11434`; old saved model connections can retain
`127.0.0.1` across rebuilds. See [model connections](../reference/model-providers.md)
and [image details](publishing-images.md).

### Rebuild only one local component

This is a **local development test**, not a published release. In the same
repository directory and with the same `.env`, use `podman-compose` (the
default provider used by Make/PowerShell):

| Change | Build | Recreate only affected services |
| --- | --- | --- |
| Dashboard | `podman-compose build dashboard` | `podman-compose up -d --no-build --no-deps dashboard` |
| Core | `podman-compose build api` | `podman-compose up -d --no-build --no-deps api worker` |
| Baseline processor services | `podman-compose build local-extractor` | `podman-compose up -d --no-build --no-deps local-extractor tesseract local-synthesizer local-embedder local-enricher model-provider-bridge` |
| Launcher frontend/native app | In `osii-launcher`: `npm ci`, then `npm run tauri dev` | Stop/restart the launcher app; no container build |

These commands work in PowerShell as well as macOS/Linux shells. If you chose
a different Compose provider for Make/PowerShell, use that same provider here.
Core/SDK changes also affect the Python installed in baseline and Toolbox
images: rebuild those before claiming a complete packaged test. The
[release scope table](runbook-releases.md#choose-what-changed) handles that
dependency automatically for publishing. Do not use `:latest` local images as
an immutable corporate release.

## Use published containers without building

**When:** use approved images on Windows, Mac or Linux without the launcher.

**Before:** IT provides Podman, a Compose provider, corporate trust and Quay
read access. Download `deployment.zip` from the approved GitLab Release.
Extract it into a **permanent deployment folder** (for example, your chosen
OSII folder under Documents), not a temporary download folder named for each
release. Keep using that same folder: Compose uses its project identity for
the library volume. If you already have a running deployment, update it in
place rather than creating a second project. No source checkout or `uv` is
required for this bundle.

**Do:** open a terminal in that folder. Copy settings **only on first install**:

```sh
# macOS/Linux
cp .env.example .env
mkdir -p osii-data/source osii-data/config
```

```powershell
# Windows PowerShell
Copy-Item .env.example .env
New-Item -ItemType Directory -Force osii-data/source, osii-data/config
```

Edit `.env` in a text editor. Keep its corporate prefix and immutable release
tag. Set `OSII_SOURCE_DIR` to your existing documents folder, and
`OSII_CONFIG_DIR_HOST` to the configuration folder just created, using
**absolute paths**. Use forward slashes on Windows, and quote paths with
spaces: `OSII_SOURCE_DIR="C:/Users/Heidi/My Documents"`. On Linux/Podman ensure
the config folder is writable by the non-root container user under your
rootless/SELinux policy; ask the administrator to provision the bind mount
rather than broadly changing permissions on your documents.

Then, on all three platforms:

```text
podman login YOUR_QUAY_HOST
podman compose pull
podman compose up -d --no-build --pull never
podman compose ps
```

Open `http://localhost:5173`; enter model connection details in **Setup** when
needed. Bundled defaults allow model-free processing first. The API's writable
config mount lets Setup persist local secrets outside the read-only source
folder. Do not post that config folder to GitLab.

Optional tools, for example Tabular only:

```text
podman compose --profile toolbox pull tabular-extractor tabular-enricher
podman compose --profile toolbox up -d --no-build --pull never tabular-extractor tabular-enricher
```

For Tesseract/OpenCV use service `tesseract-opencv`; for LLM wikis use
`readable-wiki-enricher` and `concept-entity-wiki-enricher`. Register the chosen
services in Setup using their **container-network** URLs, for example
`http://tabular-extractor:8097`, not host `localhost`. Model-backed tools also
need a configured model. The bundle contains only the six release images;
the development-only `agents`/`ocr` profiles are not distributed here.

**Check:** Core health at `http://localhost:8511/health`, dashboard opens,
process/search one file. Stop with `podman compose down`; restart with the same
`up` command and confirm the library persists. Never append `-v` to stop.

**Update:** back up library/configuration data; read the new release notes.
In the existing folder retain `.env`, paths and project name, change only
`OSII_IMAGE_TAG` to the new stack version, then `pull` and `up` as above.
Also repeat the selected optional-tool commands for that version. Image layers
with unchanged digests are reused. If release notes require new Compose
definitions, stop the old stack first, replace `compose.yaml` with the new
bundle's file in this same folder, review new settings without overwriting
`.env`, and restart. [Rollback](runbook-releases.md#rollback) uses the prior tag
and, if needed, its Compose file and compatible data backup.

**If it fails:** inspect `podman compose logs --tail 100 api worker dashboard`
and `podman ps`. Keep the project/folder that started these containers; an
unrelated `make down` cannot stop them. Never build locally to “fix” a failed
pull: check registry login, tag, network/trust and CPU architecture. A
`127.0.0.1:11434` error from a container means its saved Ollama endpoint needs
`host.containers.internal`, not an image rebuild.

### Already using the repository's Make or PowerShell scripts?

Keep your existing project and root `.env` from `.env.containers.example`.
Set its corporate prefix and pinned tag, then run `podman-compose pull` and
`make run` (Mac/Linux) or `.\scripts\osii.ps1 run` (Windows). For optional tools
use `make toolbox-run TOOL=tabular` or `.\scripts\osii.ps1 toolbox-run -Tool tabular`.
These run commands do not build. Stop with `make down` or
`.\scripts\osii.ps1 down` in the same checkout. The downloaded deployment
bundle does not contain these source-development scripts; use its plain
Compose commands instead.
