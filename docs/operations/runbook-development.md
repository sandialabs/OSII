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

**Do:** From the repository root, use one command and keep its terminal open:

```bash
# macOS/Linux: first demo, or later starts with your own files
make demo
# make dev
```

```powershell
# Windows PowerShell: first demo, or later starts with your own files
.\scripts\osii.ps1 demo
# .\scripts\osii.ps1 dev
```

**Check:** Open `http://localhost:5173` and `http://localhost:8511/health`.
Process one demonstration file. Stop with Ctrl+C in the launch terminal.

**If it fails:** Run the environment checks in [local-first operation](local-first.md).
Host Ollama uses `http://127.0.0.1:11434`; that address is *not* right from
inside a container.

**Update source:** stop with Ctrl+C, save/commit your own work, then
`git pull --ff-only` on your development branch and repeat `make dev` (or
`.\scripts\osii.ps1 dev`). The launch script refreshes its managed dependencies;
you do not rebuild images or publish a package to test local Python changes.
The root `.env.example` is optional host configuration, not the container
example. Host launch profiles prefer a configured OpenAI-compatible endpoint,
otherwise Ollama; choose/test processing methods in Setup. A running host
Ollama must have the models selected in that profile. For reproducible use of
a released source version, use a clean checkout of its `vX.Y.Z` tag instead of
pulling an unrelated branch. See the release's Python-package version before
installing `osii` into a separate notebook environment.

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
