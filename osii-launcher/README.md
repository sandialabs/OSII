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
npm run tauri dev
```

Corporate builds can prefill their approved deployment coordinates without
putting internal names in this public repository:

```bash
VITE_OSII_REGISTRY=quay.corp.example \
VITE_OSII_IMAGE_PREFIX=quay.corp.example/team/osii \
VITE_OSII_IMAGE_TAG=2026.09.14 \
npm run tauri build
```

The tag must identify a pinned release; the launcher rejects `latest`.

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
