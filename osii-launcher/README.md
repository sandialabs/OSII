# OSII Launcher

`osii-launcher/` is the independent desktop deployment application for people
running packaged OSII images. It is not part of Core, the dashboard, MCP, or the
processor toolbox.

The launcher is a Tauri 2 application with a React interface and a deliberately
small Rust host boundary. It checks Podman, prepares the Podman machine on
Windows and macOS, authenticates Podman to Quay without retaining the registry
password, validates a selected source folder from inside a container, stores
model API keys in the operating-system credential store, and starts the fixed
OSII Compose bundle for one saved library profile.

## Security and ownership boundary

The launcher owns host-level deployment operations. Core continues to own
canonical data, retrieval, RAG, and Processor API orchestration; the dashboard
continues to own the product interface. Containers must not receive the Podman
socket, and optional processors must not mount the user's source or OSII state.

Frontend code can invoke only registered, typed launcher commands. There is no
generic shell command. Quay credentials are passed to `podman login` on standard
input and then owned by Podman. Model API keys are stored under a profile ID in
Keychain, Windows Credential Manager, or Linux Secret Service and are never
returned to the webview.

## Development

Install Node.js, Rust, Podman 5 or newer, and a Compose provider, then run:

```bash
npm install
npm run tauri -- dev
```

## Corporate defaults

Use a git-ignored `.env.local` to prefill the corporate registry, image release,
and OpenAI-compatible endpoint without putting internal names in the public
repository. On macOS or Linux:

```bash
cp .env.example .env.local
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env.local
```

Edit `.env.local`:

```dotenv
VITE_OSII_REGISTRY=quay.corp.example
VITE_OSII_IMAGE_PREFIX=quay.corp.example/team/osii
VITE_OSII_IMAGE_TAG=2026.09.14
VITE_OSII_OPENAI_BASE_URL=https://models.corp.example/v1
VITE_OSII_OPENAI_EMBEDDING_MODEL=
VITE_OSII_OPENAI_CHAT_MODEL=
```

The image prefix is the shared part before `-core`, `-dashboard`, and
`-baseline-processors`. The tag must identify a pinned release; the launcher
rejects `latest`.

Run `npm run tauri -- dev` to test those defaults or
`npm run tauri -- build` to compile them into the installer. `VITE_` values are
visible in the compiled frontend, so they are suitable only for non-secret
defaults. **Never put an API key or registry password in this file.** Users enter
those in the launcher; model keys go to the operating-system credential store
and Quay credentials go directly to Podman.

In step 3, **Find available models** calls the endpoint's standard `/models`
route. It uses the API key currently entered in the form, or the stored key when
editing an existing profile. The launcher suggests a model containing `MiniLM`
for embeddings and `Gemma 4` for chat. Exact corporate defaults in `.env.local`
take precedence when supplied.

If the corporate model endpoint needs a private certificate authority during
development, start the launcher from a terminal with `OSII_CA_BUNDLE` set to the
approved PEM bundle. Production installers should rely on the certificate
authority installed in the workstation's operating-system trust store.

Frontend-only checks do not require Rust or Podman:

```bash
npm test
npm run build
```

The Tauri build bundles the repository's packaged `compose.yaml` as a resource.
The component export script rewrites that resource path for the launcher's
standalone corporate repository.

## Release shape

The intended signed artifacts are an MSI and setup EXE on Windows, a notarized
DMG on macOS, and an RPM plus AppImage on Linux. Installer signing, the bundled
Compose-provider sidecar, the signed Quay catalog, and dashboard-native app
management are the next release layer after this feasibility implementation.
