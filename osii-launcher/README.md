# OSII Launcher

`osii-launcher/` is the independent desktop deployment application for people
running packaged OSII images. It is not part of Core, the dashboard, MCP, or the
processor toolbox.

The launcher is a Tauri 2 application with a React interface and a deliberately
small Rust host boundary. It checks Podman, prepares the Podman machine on
Windows and macOS, authenticates Podman to Quay without retaining the registry
password, validates a selected source folder from inside a container, stores
non-secret library profiles, lets a user choose optional Toolbox images, and
starts the resulting OSII Compose bundle. Model endpoints and credentials are
configured after launch in Workbench **Setup**, not in the launcher.

## Security and ownership boundary

The launcher owns host-level deployment operations. Core continues to own
canonical data, retrieval, RAG, and Processor API orchestration; the dashboard
continues to own the product interface. Containers must not receive the Podman
socket, and optional processors must not mount the user's source or OSII state.

## Shared drives: connect first, then select read-only

The launcher does not mount SMB/Samba shares and never asks for, stores, or
passes along share credentials. That work belongs to the operating system. In
the launcher, choose a folder that is already available to your user account:

- **Windows:** open the share in Explorer, map it to a drive, or paste a UNC
  path such as `\\server\share\documents` into **Document folder**.
- **macOS:** connect through Finder (**Go → Connect to Server**) and select or
  paste the mounted path, normally under `/Volumes`.
- **Linux:** use the folder already mounted by your desktop or administrator.

The native folder picker cannot log in to or mount a network share. Paste an
already-connected path when it is not visible in that picker, then select
**Test container access**. The test checks both your workstation's read access
and Podman's access. A successful profile mounts the documents into OSII at
`/data/source` **read-only**. OSII writes `.osii`, catalogs, indexes, and other
derived artifacts only to its separate local library-data directory.

On macOS and Windows, Podman runs in a Linux virtual machine. If the host can
open a share but the test fails, permit the mounted folder in Podman Desktop or
the Podman machine, then test again. OSII never works around that boundary by
copying originals or mounting the share itself. See
[Shared drives and Samba](../docs/operations/shared-drives.md) for command-line
deployment details.

Frontend code can invoke only registered, typed launcher commands. There is no
generic shell command. Quay credentials are passed to `podman login` on standard
input and then owned by Podman. Provider keys entered in Workbench are written
only to that library profile's `deployment/secrets.env`; they are never stored in
the launcher profile, `.osii`, or a Toolbox container.

## Development

Install Node.js, Rust, Podman 5 or newer, and a Compose provider, then run:

```bash
npm install
npm run tauri -- dev
```

## Local Windows build output

After `npm run tauri -- build` on Windows, the NSIS installer is normally at
`src-tauri\target\release\bundle\nsis\OSII Launcher_<version>_x64-setup.exe`.
The build recreates its required Windows `.ico` from the tracked
`src-tauri/icons/icon-source.svg` when it is absent; a fresh launcher checkout
needs no manually created icon files.
To locate every Windows installer that the build produced, run this from the
`osii-launcher` directory:

```powershell
Get-ChildItem .\src-tauri\target\release\bundle -Recurse -File |
  Where-Object { $_.Extension -in ".exe", ".msi" } |
  Select-Object -ExpandProperty FullName
```

## Corporate defaults

Use a git-ignored `.env.local` to prefill the registry and image release without
putting internal names in the public repository. On macOS or Linux:

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
```

The image prefix is the shared part before `-core`, `-dashboard`, and
`-baseline-processors`. The tag must identify a pinned release; the launcher
rejects `latest`.

Run `npm run tauri -- dev` to test those defaults or
`npm run tauri -- build` to compile them into the installer. `VITE_` values are
visible in the compiled frontend, so they are suitable only for non-secret
defaults. **Never put an API key or registry password in this file.** Quay
credentials go directly to Podman; model credentials belong in Workbench Setup.

Step 3 selects optional Toolbox services. The two wiki services share one image,
so choosing both performs one pull. Tesseract/OpenCV uses its own image. The
launcher seeds registrations for selected services in the profile's `deployment/tools.toml`.
Unselected services remain available to add later. The selection
controls which images are pulled and which services are started. Workbench reads
the file immediately. The same directory contains `models.toml` and `secrets.env`.

The collapsed **Images pulled when OSII starts** panel in step 1 previews the
exact pinned images for the current profile and optional-service selection.
**Check login** only asks Podman whether it is already authenticated to Quay.
**Start OSII** runs `podman pull` for every listed image before starting Compose;
Podman reuses already-downloaded layers.

Launcher builds from before this policy change may have created Keychain entries
with service name `org.osii.launcher.openai`. The current launcher neither reads
nor deletes them. A user who tested an earlier build can remove those entries in
macOS Keychain Access; removing them is optional and does not affect saved OSII
profiles.

## Saved profiles

Profiles contain non-secret launcher settings and are stored outside the source
repository in the operating system's application-data directory:

Each profile has sibling `data/` (writable `.osii` state) and `deployment/`
(editable TOML and local secrets) directories. The original source folder can
be elsewhere, including a read-only shared drive. **Export profile** saves a
single TOML settings snapshot; **Import profile** creates a new profile. The
snapshot includes exact source paths and service URLs, so inspect it before
sharing. It excludes keys, original files, and `.osii` data. Enter credentials
again after importing; an unavailable source can be remapped before launch.
Free-form processor setting overrides are not exported because they may contain
sensitive prompt text.

- macOS: `~/Library/Application Support/org.osii.launcher/profiles.json`
- Windows: `%APPDATA%\org.osii.launcher\profiles.json`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/org.osii.launcher/profiles.json`

The launcher collapses exact historical duplicates when it loads this file and
reuses a profile when the same library name and canonical source folder are saved
again. **Remove selected** deletes only the saved profile record. It does not
delete the source folder or the launcher's indexed library-data directory.

Frontend-only checks do not require Rust or Podman:

```bash
npm test
npm run build
```

## Theme colors

The launcher theme is controlled by the custom properties at the top of
`src/styles.css`:

```css
:root {
  --ink: #25343b;
  --muted: #68757b;
  --border: #d9e0e2;
  --turquoise: #008f91;
  --turquoise-dark: #006f71;
  --orange: #e76513;
  --orange-dark: #bc4800;
}
```

Replace these values with the approved corporate style-guide colors. `--ink`,
`--muted`, and `--border` control neutral text and outlines. `--turquoise` and
`--turquoise-dark` control connection states, ordinary buttons, links, and focus
indicators. `--orange` and `--orange-dark` control step markers, warnings,
selection accents, and the primary deployment action. Keep the page, panels,
inputs, logs, and diagnostic output white unless the corporate guidelines require
otherwise.

Use each darker variant for text and hover states, and verify that text, controls,
focus indicators, and status states retain accessible contrast. Theme values are
ordinary frontend CSS and contain no corporate configuration or credentials.

To preview only the interface without Rust, Podman, or a Tauri build:

```bash
npm run dev
```

Open `http://127.0.0.1:1420`, edit `src/styles.css`, and use the live preview to
apply the corporate guidelines. Deployment actions are unavailable in this
browser-only preview. Run `npm test` and `npm run build` after finalizing the
palette.

The Tauri build bundles the repository's packaged `compose.yaml` as a resource.
The component export script rewrites that resource path for the launcher's
standalone corporate repository.

## Built-in demo

Select **Load built-in demo** in step 2 to create and select an `OSII built-in
demo` profile. It copies the already-packaged Purcell PDF plus the Iris and Wine
sample datasets exported from scikit-learn into the launcher's application-data
directory. It does not need Python, scikit-learn, a source checkout, or a shared
drive, and it never modifies a user-selected library folder.

The demo uses the image prefix and pinned tag currently shown in step 2. Log in
to Quay if necessary, then select **Start OSII** as usual. The launcher still
pulls the approved images and starts only the bundled baseline services. Loading
the demo again preserves any files already present in its local source folder.

## Advanced deployment view

After saving a library, select **Advanced view** beside the deployment controls.
The panel shows the exact generated `compose.env`, the generated Compose override,
their full workstation paths, and the ordered commands used to pull and start the
bundle. It opens automatically when a start command fails and includes the latest
error output. API keys and registry passwords are never included.

The launcher uses the generated `compose.env` with both supported Compose
providers and mounts the library profile's configuration directory into Core.

## If a Quay image pull fails

**Start OSII** pulls Core, the dashboard, and baseline processors before it
starts Compose. It also pulls each distinct optional Toolbox image chosen
in the library profile. If a pull fails, open **Advanced view**. It shows the
exact recovery commands for the selected library profile.

On Windows, open PowerShell and run the displayed `podman login` command, then
the three `podman pull` commands in order. `podman login` prompts for your Quay
credentials. When every displayed pull succeeds, return to the launcher and select
**Start OSII** again. Do not start Compose directly: the launcher generates the
library-specific mounts and model/tool configuration.

For a manual example, replace these three values with the registry, image
prefix, and pinned tag shown in the launcher:

```powershell
$registry = "quay.corp.example"
$prefix = "quay.corp.example/team/osii"
$tag = "2026.09.14"

podman login $registry
podman pull "${prefix}-core:${tag}"
podman pull "${prefix}-dashboard:${tag}"
podman pull "${prefix}-baseline-processors:${tag}"
```

## Release shape

With the required corporate runners and signing credentials configured, the
current release pipeline produces a signed setup EXE for Windows and notarized
DMGs for Intel and Apple-silicon macOS. MSI, RPM, and AppImage packages remain
future distribution options. A bundled Compose-provider sidecar, signed Quay
catalog, and dashboard-native app management are also planned release
enhancements.
