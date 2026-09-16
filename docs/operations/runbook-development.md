# Development runbooks

These paths are for developers. Non-developers should use the
[desktop launcher](runbook-desktop.md).

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
