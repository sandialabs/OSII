# Public development and corporate releases

For the short action checklist, start with [What are you trying to do?](runbooks.md).
This page is the one-time setup and policy reference, not a daily runbook.

**Current operating mode: manual releases, no corporate runners.** Follow the
[manual release checklist](runbook-releases.md). GitLab stores reviewed source,
packages and release downloads; your workstations perform the builds. The CI
configuration below is for later enablement, not a prerequisite for releasing.

OSII has one codebase and two environments:

| Public GitHub | Corporate GitLab |
| --- | --- |
| Develop and review portable source | Add approved internal configuration |
| Run fast tests on Python 3.12 and Linux | Repeat validation locally; runners later |
| Build the Python package on a Core/full release tag | Publish the Python package only when Core/SDK changes |
| Optionally publish `osii` to public PyPI | Build signed desktop installers |
| Never contain corporate names or secrets | Build AMD64/ARM64 images and push corporate Quay |

GitHub is not the corporate deployment system. GitLab is the source for
corporate releases and the place where protected credentials are available.

## What happens in GitHub

Every pull request and commit to `main` runs two jobs:

1. Core, processor, packaging, and documentation checks on Linux/Python 3.12.
2. Dashboard and launcher frontend tests and builds on Linux.

Routine pushes do not build containers, start the full stack, or run three
operating-system jobs. This keeps feedback useful and reduces failed-run email.
GitHub notification preferences still control which failures GitHub emails.

A `vX.Y.Z` tag additionally tests installation on Linux, macOS, and Windows.
For a Core/full release it stores the wheel and source distribution as workflow
artifacts. It publishes to PyPI only when both of these administrative steps
are complete:

- repository variable `OSII_PUBLISH_PYPI` is `true`;
- PyPI trusts `.github/workflows/ci.yml` through the `pypi` environment.

Until then, a Core/full GitHub tag validates and builds the package but does
not upload it. UI/launcher/Toolbox-only tags do not create a new Python package.
GitHub does not publish OSII containers or corporate installers.

For baseline security without more container CI, turn on GitHub secret
scanning/push protection, Dependabot alerts, and CodeQL default setup in the
public repository's Security settings. Those are one-time administrator
settings; they are not configured by the OSII workflow file. Keep routine
GitHub CI to portable tests and builds. See GitHub's
[CodeQL default-setup instructions](https://docs.github.com/en/code-security/code-scanning/enabling-code-scanning/configuring-default-setup-for-code-scanning)
and [secret-scanning instructions](https://docs.github.com/en/code-security/secret-scanning/enabling-secret-scanning-features/enabling-secret-scanning-for-your-repository).

## Bring public changes into the corporate repository

Do this from a corporate workstation that can reach both repositories. The
examples assume the corporate checkout is already on its normal development
branch and the public repository is named `public`.

One-time setup:

```bash
git remote add public https://github.com/sandialabs/OSII.git
git remote -v
```

For each update:

```bash
git switch main
git pull --ff-only origin main
git fetch public main
git switch -c import/public-YYYY-MM-DD
git merge --no-ff public/main
```

Then:

- resolve conflicts in the import branch;
- preserve corporate-only endpoints, certificates, policies, and runner setup;
- run the local focused tests;
- push the branch to corporate GitLab;
- open a merge request into corporate `main`;
- review local test evidence and the public commits plus corporate adaptations;
- merge the request; do not tag from the import branch.

If corporate policy forbids a direct remote to GitHub, transfer an approved
Git bundle instead:

```bash
# On a public-connected workstation
git fetch origin main
git bundle create osii-public.bundle origin/main

# On the corporate workstation
git fetch /approved/path/osii-public.bundle origin/main:refs/remotes/public/main
```

Continue with the same import branch, merge request, and review steps.

## Configure GitLab once

For today's manual route, use the [manual setup checklist](runbook-releases.md#configure-gitlab-once).
The remainder of this section describes **future runner setup**. Do not run a
tag pipeline for a version that was already published manually.

The checked-in `.gitlab-ci.yml` expects these runner tags:

- `osii-linux-amd64`
- `osii-linux-arm64`
- `osii-windows-x64`
- `osii-macos-arm64`
- `osii-macos-x64`

Linux image runners need Python 3.12, `uv`, Node.js 22, Podman,
`podman-compose`, `skopeo`, Git, Make, and access to approved mirrors. Desktop
runners also need Node.js 22, Rust, and the Tauri prerequisites. Windows needs
the approved code-signing certificate. macOS needs Apple signing and
notarization credentials.

Protect corporate `main`, the `v*` tag pattern, `corporate-release`, and
`corporate-promotion` environments. Require a merge request for imported changes
and restrict release approval and tag creation to release maintainers.

Set these protected or environment-scoped CI variables:

| Variable | Purpose |
| --- | --- |
| `OSII_QUAY_REGISTRY` | Corporate Quay hostname |
| `OSII_IMAGE_PREFIX` | Full prefix before `-core`, `-dashboard`, and other suffixes |
| `OSII_QUAY_USER`, `OSII_QUAY_PASSWORD` | Robot account allowed to publish OSII images |
| `OSII_BASE_IMAGE` | Approved RHEL/UBI reference pinned by SHA-256 digest |
| `OSII_CA_BUNDLE` | Runner path to the approved corporate PEM bundle, when needed |
| `OSII_TESSERACT_SOURCE_URL` | Approved mirror for the pinned Tesseract source |
| `OSII_LEPTONICA_SOURCE_URL` | Approved mirror for the pinned Leptonica source |
| `OSII_TESSDATA_BASE_URL` | Approved mirror base for the pinned language data |
| `OSII_MODEL_BASE_URL` | Non-secret default model endpoint compiled into the launcher |
| `OSII_EMBEDDING_MODEL`, `OSII_CHAT_MODEL` | Optional approved model defaults |
| `OSII_CATALOG_URL` | Credential-free HTTPS raw URL for the reviewed launcher `catalog.json` |
| `OSII_CATALOG_PROJECT` | Protected GitLab `group/project` that owns that catalog; allow this release project's Job Token to clone and, on supported GitLab versions, push release branches there |
| `OSII_CATALOG_PATH`, `OSII_CATALOG_TARGET_BRANCH` | Optional catalog path and protected target branch; defaults are `catalog.json` and `main` |
| Windows signing variables | `OSII_WINDOWS_CERTIFICATE_THUMBPRINT`, `OSII_WINDOWS_TIMESTAMP_URL` |
| Apple signing variables | `APPLE_SIGNING_IDENTITY`, `APPLE_ID`, `APPLE_PASSWORD`, `APPLE_TEAM_ID` |

Store passwords and signing credentials as masked, protected variables. Install
package-manager registry and CA configuration on the runners so `uv`, pip,
npm, Cargo, and OS package commands use approved sources.

### Corporate defaults

In the corporate repository only, commit `corporate/osii.toml` with *non-secret*
values. The generic helper and CI read the same file, so Quay paths, approved
base image, mirror URLs, and model defaults are entered once. For example:

```toml
[defaults]
OSII_QUAY_REGISTRY = "quay.internal.invalid"
OSII_IMAGE_PREFIX = "quay.internal.invalid/ai-ready-everything/osii"
OSII_BASE_IMAGE = "quay.internal.invalid/approved/ubi9@sha256:REPLACE_WITH_64_HEX_DIGEST"
OSII_TESSERACT_SOURCE_URL = "https://artifacts.internal.invalid/tesseract.tar.gz"
OSII_LEPTONICA_SOURCE_URL = "https://artifacts.internal.invalid/leptonica.tar.gz"
OSII_TESSDATA_BASE_URL = "https://artifacts.internal.invalid/tessdata"
OSII_MODEL_BASE_URL = "https://models.internal.invalid/v1"
OSII_EMBEDDING_MODEL = ""
OSII_CHAT_MODEL = ""
OSII_CATALOG_URL = "https://gitlab.internal.invalid/osii/release-config/-/raw/main/catalog.json"
```

Replace the illustrative values with approved real ones. The helper rejects
unknown keys, placeholders, non-HTTPS endpoints, and unpinned base images.
Do not put API keys, Quay passwords, signing credentials, certificate contents,
or GitLab project credentials in this file. CI variables override these defaults
and hold secrets. `OSII_CATALOG_PROJECT` is intentionally a CI variable: its
Job Token clone permission, and cross-project push permission when supported,
must be granted by the separate protected catalog project.
The catalog **repository** stays protected for writes and merge requests, but
the HTTPS URL compiled into the launcher must be readable by approved
workstations without a GitLab personal token. Publish its reviewed raw file
through an internal read-only endpoint if GitLab's raw-file permission would
otherwise require interactive authentication; the launcher never embeds or
sends a GitLab credential.
On a workstation, validate and create ignored `.env` and launcher `.env.local`
without overwriting any existing local files:

```bash
uv run --no-project --python 3.12 python scripts/corporate_config.py check --version 0.1.1
uv run --no-project --python 3.12 python scripts/corporate_config.py write --version 0.1.1
```

Those files are for local Compose/frontend use, **not required by manual release
commands**, which read TOML directly. To compare new defaults without replacing
existing settings (including private credentials), stage them separately:

```text
uv run --no-project --python 3.12 python scripts/corporate_config.py write --version 0.1.1 --output-dir release/settings-preview
```

Review `release/settings-preview/.env` against your existing `.env`, then apply
only the intended differences. A new release tag must not reset users' source
folders, saved connections or library data. `write` refuses to overwrite a
different existing file; it does not merge or erase local settings.

### Configuration ownership and precedence

| File or location | Used by | Rule |
| --- | --- | --- |
| `corporate/osii.toml` | Manual release helper and future GitLab jobs | Reviewed non-secret corporate defaults; process environment overrides |
| `release.toml` | Release preparation/build/assembly | Stack version, prior tag, scope, Python version; never derive release version from `.env` |
| Root `.env` from `.env.example` | Host-Python development | Host addresses; optional settings; not a production release manifest |
| Root `.env` from `.env.containers.example` or corporate generator | Make/PowerShell container commands, Compose | Command options override shell variables, which override `.env` |
| `osii-launcher/.env.local` | Direct frontend/Tauri builds | Non-secret compiled defaults; manual installer helper supplies authoritative `VITE_OSII_*` environment values instead |
| Deployment bundle `.env` | End-user Compose | Pinned registry/tag and existing absolute source/config paths; keep across updates |
| Saved library profile + catalog | Installed launcher | Catalog pins approved image digests; root repository `.env` is not read |
| Workbench Setup's `models.toml` / `secrets.env` | Running Core and model bridge | Local model connections/keys; process-injected values can take precedence |

Do not combine the host and container examples: `127.0.0.1` means this process's
machine; containers use `host.containers.internal` for a model server on the
workstation. The examples and generated deployment settings select model-free
processing by default; development launch scripts also apply their selected
provider profile. Configure and test the desired model explicitly in Setup.

Corporate generated settings include the writable `/config` mount, opt-in
Setup writes for a personal workstation, and approved model defaults. A managed
shared deployment should set `OSII_ALLOW_LOCAL_CONFIG_WRITES=false` and inject
credentials through its approved mechanism. `.env` and TOML are not interchangeable:
the release helper deliberately does not auto-load an old development `.env`.

The example file is **never added to public GitHub**. Keep it on the corporate
branch when importing upstream changes. The public GitHub workflow fails if a
`corporate/osii.toml` is accidentally present.

## Make a corporate release

On a release-preparation branch, use `scripts/release_plan.py prepare` with the
next stack version, prior tag, and `full`, `core`, `ui`, `launcher`, or one
`toolbox-*` scope. This updates the launcher versions, and it updates the
Python package version only for Core/full releases. The complete copy-pasteable
procedure is in the [corporate release runbook](runbook-releases.md).

For the **first corporate release**, use `--scope full --previous-tag=`.
An imported public tag is not a prior corporate release because there are no
corporate images to reuse. For later normal releases, use the preceding
release-plan tag. Commit and merge the plan into corporate `main`. Create a
protected tag on that merged commit using GitLab's **Code → Tags → New tag** or
these commands:

```bash
git switch main
git pull --ff-only origin main
git tag -a v0.1.1 -m "OSII 0.1.1"
git push origin v0.1.1
```

**Today:** follow the manual runbook after tagging. No runner will build or
upload these outputs for you. **After runners are provisioned and validated,**
the protected tag pipeline validates the commit and pauses at
`approve-release`. After a release maintainer approves it, GitLab:

1. builds and tests the `osii` wheel and source distribution only when Core/SDK changes;
2. builds changed images natively for Linux AMD64/ARM64, and copies unchanged
   image manifests by verified digest to the new immutable version;
3. smoke-tests changed images and pushes architecture tags to corporate Quay;
4. builds signed Windows and Intel/Apple-silicon macOS launchers with corporate
   registry, image tag, and model defaults;
5. assembles and verifies the multi-architecture image manifests;
6. publishes `osii` to the GitLab Python package registry only when Core changes;
7. creates a GitLab Release containing installers, `deployment.zip`, image
   digests, and SHA-256 checksums;
8. resolves each known Quay release image to its immutable manifest digest,
   validates every existing catalog reference, and opens a release-branch merge
   request in the protected catalog project. The job never enumerates Quay tags
   or writes `:latest` into the catalog.

Review and merge that catalog merge request after confirming the exact image
mapping. The launcher sees the new approved Stack only after this review; until
then it continues to use its last valid cached catalog if the catalog endpoint
or Quay is temporarily unavailable.
For the first release, the same job creates `catalog.json` from an empty
version-1 catalog and adds the first complete Stack; no hand-edited placeholder
digest is required.

The catalog job uses a GitLab Job Token for Git and the API. Confirm that the
corporate GitLab version supports the required cross-project push settings.
Standard GitLab job-token permissions document read-only Merge Requests API
access, not creation. If the catalog branch push succeeds but the create-MR
API call fails, open the merge request manually or add an approved corporate
authentication layer. Do not put a personal token in the repository.

Tags are immutable. Whether the same pipeline can be retried depends on which
external outputs exist; follow the
[failed-tag recovery decision table](runbook-releases.md#failed-tag-recovery).
When a new version is required, never reuse the old tag or image version. After
clean workstation acceptance, the separate protected `promote-latest` job may
move corporate Quay's `:latest` aliases. The launcher and deployment bundles
still use immutable versions; `latest` is not a deployment rollback mechanism.

## Local validation without runners

Run from the repository root before merging release preparation. Save the
results in the merge request; a pending pipeline is not a passing test.

```text
uv run --frozen --python 3.12 --package osii --extra dev python -m pytest osii-core/tests osii-core/processor-sdk/tests osii-toolbox/tests/test_packaging.py -q
uv run --no-project --python 3.12 python scripts/check_docs_links.py
uv run --no-project --python 3.12 --with mkdocs-material mkdocs build --strict
```

For dashboard changes, from `osii-dashboard/dashboard`: `npm ci`,
`npm test --if-present`, `npm run build`. For launcher changes, from
`osii-launcher`: `npm ci`, `npm test`, `npm run build`, then
`cargo test --manifest-path src-tauri/Cargo.toml` on a configured native host.
Run changed processor services' own tests as described in their READMEs.
Return to the root before release commands. Full releases need both frontend
checks and the package installation check from the manual release runbook.
Build smoke tests are not a substitute for the clean-user test below.

## Code signing on workstations

Signing identifies the publisher and detects modification of the executable.
It is separate from Git tags, image digests, Quay login, and SHA-256 download
checksums. You do not need CI to sign. Ask corporate IT to provision the
identity and access once; do not purchase/export certificates ad hoc.

### Windows

Ask IT for a code-signing identity usable by Windows SignTool, its certificate
thumbprint, the approved timestamp URL, and the trust policy on user devices.
An internal certificate is useful only where its chain is trusted; a valid
signature does not guarantee SmartScreen reputation. The current OSII helper
uses Tauri's certificate-thumbprint signing route. An IT-managed cloud signing
service needs an approved Tauri `signCommand` adaptation; these two variables
alone do not configure cloud signing.
[Tauri Windows signing](https://v2.tauri.app/distribute/sign/windows/).

In native PowerShell, after IT installs the signing identity/private-key access:

```powershell
Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Format-Table Subject, Thumbprint, NotAfter
$env:OSII_WINDOWS_CERTIFICATE_THUMBPRINT = Read-Host 'Approved certificate thumbprint'
$env:OSII_WINDOWS_TIMESTAMP_URL = Read-Host 'Approved timestamp URL'
uv run --no-project --python 3.12 python scripts/corporate_release.py installer --manual --target windows-x64
Get-AuthenticodeSignature -LiteralPath release/installers/OSII-0.1.1-windows-x64.exe
```

The helper requires `Valid` before staging. Confirm the expected publisher,
not merely any valid signer. Keep the private key in IT's approved certificate
store/hardware mechanism, never in the repository or an installer transfer.

### macOS

Ask IT for a **Developer ID Application** identity and private-key access in
the Mac's keychain, the Apple team ID, and approved notarization credentials.
Signing identifies your organization; notarization is Apple's additional
distribution check. Corporate network access to Apple's service is required.
The current helper uses the Apple-ID route with an **app-specific password**,
not your normal account password. API-key notarization is a separate supported
Tauri option but is not wired into this helper.
[Tauri macOS signing and notarization](https://v2.tauri.app/distribute/sign/macos/).

In the Mac terminal, use the identity IT provides:

```sh
security find-identity -v -p codesigning
export APPLE_SIGNING_IDENTITY='Developer ID Application: Your Organization (TEAMID)'
export APPLE_TEAM_ID='TEAMID'
export APPLE_ID='your-approved-apple-id'
```

Load `APPLE_PASSWORD` from the approved secret manager into this session, then
run the manual installer command. Do not type the secret literally into shell
history. For a temporary interactive session without a secret-manager command,
these hidden-input prompts are shell-specific:

```sh
# macOS default zsh
read -rs 'APPLE_PASSWORD?Apple app-specific password: '
export APPLE_PASSWORD
```

```sh
# Bash instead
read -r -s -p 'Apple app-specific password: ' APPLE_PASSWORD
export APPLE_PASSWORD
```

After building, `unset APPLE_PASSWORD`. The helper runs `xcrun stapler validate`
on the DMG. Test the actual downloaded DMG on another managed Mac too. If IT
cannot supply signing/notarization yet, use the approved Compose path; do not
tell non-developers to disable Gatekeeper as routine installation guidance.

## Internal Python publication

One-time workstation setup: use the project ID shown by GitLab and create a
non-secret `.pypirc` in your user home directory (Windows: `%USERPROFILE%`).
Replace this illustrative URL; do not commit the file:

```ini
[distutils]
index-servers = osii-internal

[osii-internal]
repository = https://gitlab.internal.invalid/api/v4/projects/123/packages/pypi
```

Twine's `--repository osii-internal` selects that upload destination. Use an
approved deploy/access token with package-write permission via interactive
prompt or the workstation secret manager. The username depends on the token
type; ask the GitLab administrator. Keep credentials out of this file and URLs.
Configure TLS trust; never disable certificate verification to upload.
See [GitLab Python registry authentication](https://docs.gitlab.com/user/packages/pypi_repository/).

For **consumers**, IT configures pip's internal index and read credentials once
on each workstation. Then the package-only update is:

```text
python -m pip install --upgrade osii==0.1.1
```

Use the release's `python-package.json` version, which may be older than the
stack version. The `osii` package includes `osii.processor_sdk`; it does not
install the dashboard, launcher, Podman, or an entire running stack. Avoid
combining an untrusted public extra index with internal package names.

## Non-developer acceptance check

Before announcing the release, test on a workstation with no OSII checkout or
cached OSII images:

- install the matching signed OSII Launcher from the GitLab Release;
- confirm Podman Desktop and a Compose provider are available;
- open the launcher, refresh its catalog and choose/pull the approved Stack;
- sign in to Quay, choose a readable document folder, and test container access;
- start OSII and open the dashboard;
- ingest a document and complete one search/chat workflow;
- enable OpenCV/Tesseract or Tabular only when needed, then test its descriptor
  and one real document;
- stop and restart OSII and confirm the library remains available.

Also test `deployment.zip` in a fresh, stable folder on Windows and Mac/Linux:
copy settings, configure absolute source/config paths, pull, start, configure a
model in Setup, process a file, stop/restart, then roll back. Never use a new
Compose project directory for an upgrade test without intentionally migrating
its library volume. Record OS/CPU, stack tag, installer checksum, model endpoint
(no key), result, and tester in the Release description. Advertise only tested
installer targets; a missing Intel Mac installer is not an ARM64 installer.

The release is ready for non-developers only after this clean-workstation test
passes. Record any confusing step as a launcher or documentation issue for the
next patch release.

## Inside versus outside checklist

### Outside: public GitHub

- Keep paths, examples, and defaults portable.
- Use Python 3.12 as the canonical runtime.
- Never commit corporate hosts, certificates, tokens, or signing material.
- Merge normal development; create a public tag only for a deliberate public
  package candidate.
- Treat PyPI publishing as optional and independent of corporate delivery.

### Inside: corporate GitLab

- Import public changes through a branch and merge request.
- Apply internal endpoints and policy in the corporate layer.
- Protect `main` and `v*`; use approved workstation credentials now and protected
  runners/variables/environments when automation is enabled.
- Publish packages, signed installers, and immutable images only from a
  protected corporate tag.
- Keep one approved release available for rollback.
- Give non-developers the signed launcher from the GitLab Release rather than a
  source checkout or build instructions.

References: [GitLab PyPI registry](https://docs.gitlab.com/user/packages/pypi_repository/),
[GitLab release pipelines](https://docs.gitlab.com/user/project/releases/release_cicd_examples/),
and [GitLab workflow rules](https://docs.gitlab.com/ci/yaml/workflow/).
