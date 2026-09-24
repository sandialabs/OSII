# Manual corporate release runbook

**No GitLab runners are needed for this procedure.** You build on workstations,
push images to corporate Quay, and upload files to a GitLab Release yourself.
A Git tag records source; it does not build or distribute anything by itself.

Start with the table, then follow steps 1–7. Each step says where to run it.
Commands are from the repository root unless noted. Single-line `uv` and
`git` commands work in macOS/Linux shells and Windows PowerShell.

## Choose what changed

| Change | `--scope` | Images rebuilt on each architecture | Python package |
| --- | --- | --- | --- |
| First release, shared build/base/Compose changes, or several components | `full` | All six | New |
| Core, public Python API, or Processor SDK | `core` | Core, baseline-processors, Tesseract/OpenCV, Tabular, LLM wikis | New |
| Dashboard | `ui` | Dashboard only | Reuse |
| Launcher | `launcher` | **None** | Reuse |
| Tesseract/OpenCV Toolbox | `toolbox-tesseract-opencv` | Tesseract/OpenCV only | Reuse |
| Tabular Toolbox | `toolbox-tabular` | Tabular only | Reuse |
| LLM-wiki Toolbox | `toolbox-llm-wikis` | LLM wikis only | Reuse |

Unchanged images are copied by digest to the new stack tag, **not rebuilt**.
They retain their original embedded component version. `images.json` records
the actual release composition; do not expect a copied Core image to report
the new stack tag internally.

**Current policy:** every new stack version gets newly built, signed launcher
installers for the desktop platforms you distribute. A dashboard-only release
therefore builds one image per CPU architecture plus the launchers—not Core
or the toolbox. Existing compatible launchers can discover new Stacks through
the catalog without being reinstalled; a launcher bug fix requires installing
the new launcher. There is no automatic installer-update step in this runbook.

A change to baseline services under `osii-core/` is `core`, not an independent
Toolbox scope. A new image outside these six requires release-tooling changes;
do not silently omit it. Scope checks reject mixed/shared changes.

## Configure GitLab once

**Before:** use a corporate checkout whose `origin` is corporate GitLab. Check
`git remote -v`. Have a maintainer protect `main` and `v*`, enable Releases and
Package Registry, and grant your approved publishing identity access.

- While there are no runners, have the maintainer disable project CI/CD or
  cancel pending pipelines and explicitly arrange reviewed local-test evidence
  for merges. Do not wait for a pending pipeline to publish your release.
  Never start the tag pipeline later for an already manually published tag.
- Commit the non-secret [corporate defaults](corporate-deployment.md#corporate-defaults)
  only inside GitLab. Package-manager mirrors and trust must also be configured
  on each build machine. TOML source-mirror keys cover OCR artifacts, not all
  pip/npm/Cargo downloads.
- Arrange Quay write access for the six `osii-*` repositories under
  `ai-ready-everything`; consumers need only read access.
- Arrange a reviewed catalog repository and a credential-free internal HTTPS
  URL serving its `catalog.json`. A private GitLab raw URL that returns a login
  page will not work. Initialize that repository's `main` branch with a README
  in GitLab if it is empty. No fake initial catalog is required.
- Install GitLab CLI `glab` for manual file uploads. Run
  `glab auth login --hostname YOUR_GITLAB_HOST` interactively and
  `glab auth status`. Do not put tokens in TOML, Git, or command history.
- Complete [signing setup](corporate-deployment.md#code-signing-on-workstations)
  for each desktop platform you will distribute.

### Which machine does which work?

| Work | Machine and shell | Tools |
| --- | --- | --- |
| Prepare source, test Python, build wheel, upload release | Windows PowerShell, macOS, or Linux | Git, `uv` with Python 3.12; Node 22 for frontend tests; `glab` for upload |
| Build Linux AMD64 images | AMD64 Linux, Intel Mac with Podman VM, or Windows x64 **inside an IT-provisioned WSL2 Linux shell** | Podman, Skopeo, Git, `uv`/Python 3.12 |
| Build Linux ARM64 images | ARM64 Linux or Apple Silicon Mac with Podman VM | Same tools |
| Assemble/copy manifests, generate catalog, promote aliases | One macOS/Linux/WSL publishing shell | Podman, Skopeo, Git, `uv`/Python 3.12 |
| Build Windows x64 launcher | Native Windows x64 PowerShell, **not WSL** | Node 22, Rust MSVC, Visual Studio C++ build tools, WebView2/Tauri prerequisites, signing identity |
| Build Mac launcher | Matching Apple Silicon or Intel Mac | Node 22, Rust, Xcode command-line tools, signing identity |

Use an actual Linux checkout and Linux tools inside WSL, not Windows Python
or an assumed native Windows Skopeo installation. IT must provision its Podman
engine/connection and trust; Windows Podman Desktop login and Linux Skopeo
login are not automatically shared. Container images are Linux images:
**AMD64 Tesseract does not have to be built on Windows.** Avoid emulation for
release builds. Check `podman info --format '{{.Host.OS}}/{{.Host.Arch}}'`.

You need both native container architectures, but not CI runners. If a machine
or signing identity is unavailable, do not claim that platform is tested.
The bundle step lets you explicitly list available signed desktop installers;
Linux users have the Compose/source routes, not a supported Linux installer
in this release helper.

## 1. Prepare and tag the source

**When:** implementation changes are committed/reviewed on corporate `main`.
Reserve an unused version across Git tags, Quay tags, Python packages and
GitLab release assets. Examples start at `0.1.1`; substitute your version
throughout. Do not type these examples over an existing release.

### First corporate release

An imported source tag does not imply corporate images exist. If
`release.toml` currently says `0.1.0`, prepare `0.1.1`:

```text
git switch main
git pull --ff-only origin main
git switch -c release/v0.1.1
uv run --no-project --python 3.12 python scripts/release_plan.py prepare --version 0.1.1 --scope full --previous-tag= --dry-run
uv run --no-project --python 3.12 python scripts/release_plan.py prepare --version 0.1.1 --scope full --previous-tag=
uv run --no-project --python 3.12 python scripts/release_plan.py check
```

`--previous-tag=` is intentionally empty and works in PowerShell too. The
version must increase from the current plan. First release is always full.

### Later full or component release

For a dashboard change after successful `v0.1.1`, use this **instead**:

```text
git switch main
git pull --ff-only origin main
git switch -c release/v0.1.2
uv run --no-project --python 3.12 python scripts/release_plan.py prepare --version 0.1.2 --scope ui --previous-tag v0.1.1 --dry-run
uv run --no-project --python 3.12 python scripts/release_plan.py prepare --version 0.1.2 --scope ui --previous-tag v0.1.1
uv run --no-project --python 3.12 python scripts/release_plan.py check
```

Change only the scope to `launcher`, `core`, or a named `toolbox-*` scope
for those cases. Reuse requires the preceding corporate release to be complete.
If it failed, use [recovery](#failed-tag-recovery), not a selective release.

### Review, merge, tag

Preparation updates `release.toml` and these five launcher version files:
`package.json`, `package-lock.json`, `src-tauri/Cargo.toml`,
`src-tauri/Cargo.lock`, `src-tauri/tauri.conf.json`.
Full/Core also update `osii-core/pyproject.toml` and the local package version
in root `uv.lock`; other scopes keep the Python version unchanged.

Run the [local validation checklist](corporate-deployment.md#local-validation-without-runners).
Then, for the first-release example:

```text
git diff --stat
git add release.toml osii-core/pyproject.toml uv.lock osii-launcher/package.json osii-launcher/package-lock.json osii-launcher/src-tauri/Cargo.toml osii-launcher/src-tauri/Cargo.lock osii-launcher/src-tauri/tauri.conf.json
git commit -m "release: prepare OSII 0.1.1"
git push -u origin release/v0.1.1
```

Open and review the GitLab merge request; attach local test results, then merge.
The extra Core/lock paths above are unchanged for non-Core releases. Inspect
the diff before staging; never include unrelated local changes.

```text
git switch main
git pull --ff-only origin main
uv run --no-project --python 3.12 python scripts/release_plan.py check
git tag -a v0.1.1 -m "OSII 0.1.1"
git push origin v0.1.1
git switch --detach v0.1.1
```

On **each** build machine, fetch `origin` and tags and check out this same tag.
The manual helper requires a clean checkout at that exact tag, checks it is
on fetched `origin/main`, and checks scope and versions. You verify in GitLab
that the remote tag is protected and matches the reviewed commit.

**If it fails:** stop at the reported scope/version/config error. Do not
disable checks or force-push a tag. All following examples use `0.1.1`;
for a later release use its new version.

## 2. Load settings and preview the work

**Before:** put reviewed non-secret values in `corporate/osii.toml`.
The manual helper reads it automatically; it does **not** load root `.env`.
Shell environment overrides TOML. No need to copy settings into five terminals.

```text
uv run --no-project --python 3.12 python scripts/corporate_config.py check --version 0.1.1
uv run --no-project --python 3.12 python scripts/corporate_release.py preflight --manual
uv run --no-project --python 3.12 python scripts/corporate_release.py images --manual --dry-run
```

The preview lists what will build/copy and whether the Python package is reused.
It performs no registry checks, writes, builds or uploads; it does not prove
credentials or machines are ready. Real commands repeat tag/checkout checks.

Use `--config PATH` if the reviewed TOML is elsewhere. A machine-specific
`OSII_CA_BUNDLE` belongs in the local environment; use forward slashes in
Windows paths. IT must install registry and package-manager trust separately.

**Check:** the preview matches the first table. An old exported
`OSII_IMAGE_PREFIX` or `OSII_BASE_IMAGE` overrides the TOML: clear stale
variables before continuing. Do not override build inputs for a selective
release; change reviewed TOML and prepare a full release.

## 3. Build only the selected images, then assemble once

**Where:** macOS/Linux/WSL publishing shells. Skip native image-build commands
for `launcher` scope; still run assembly to copy the unchanged manifests.

On each publishing machine, log in interactively to **both** tools using your
corporate Quay hostname:

```text
podman login YOUR_QUAY_HOST
skopeo login YOUR_QUAY_HOST
```

On the native AMD64 engine:

```text
uv run --no-project --python 3.12 python scripts/corporate_release.py images --manual --arch amd64
```

On the native ARM64 engine:

```text
uv run --no-project --python 3.12 python scripts/corporate_release.py images --manual --arch arm64
```

These build/push only the scope's images as `X.Y.Z-amd64` or `X.Y.Z-arm64`,
then smoke-test their entry points. Do not substitute `make build` or
`make publish-multiarch`: those do not read the selective release plan.

After **both** succeed, on one publishing machine only:

```text
uv run --no-project --python 3.12 python scripts/corporate_release.py assemble --manual
```

Assembly checks both changed-image architectures, creates final immutable
multi-architecture tags, copies unchanged images with Skopeo
`--all --preserve-digests`, and verifies digests/AMD64/ARM64 for all six.
It writes ignored `release/images.json` and `release/python-package.json`.
It never rebuilds images. Quay may reuse existing blobs during copies.

**If it fails:** do not blindly rerun a completed image build or assembly.
Existing tags are rejected. Inspect which outputs exist using the
[recovery table](#failed-tag-recovery); TLS/auth failures are not “tag absent.”

## 4. Build the Python package only for full/Core

**Where:** any prepared build workstation. Skip this entire step for
UI/launcher/Toolbox scopes; users keep the existing Python package version.

```text
uv run --no-project --python 3.12 --with build python scripts/check_python_distribution.py
uv build osii-core --out-dir release/python
uv run --no-project --python 3.12 --with twine python -m twine check release/python/osii-0.1.1-py3-none-any.whl release/python/osii-0.1.1.tar.gz
```

**Check:** matching wheel and source archive exist under `release/python/`.
Use the approved package mirrors on this machine. A container build installs
Core from tagged source; it does not require uploading the wheel first.

**If it fails:** fix/test before publishing. Preserve old output separately;
never upload every file in an old `release/python` directory by wildcard.

## 5. Build the launcher installers

**Before:** complete [workstation signing](corporate-deployment.md#code-signing-on-workstations).
Build from the same tagged source with the same TOML on each native desktop.
The helper injects `VITE_OSII_*` values directly, overriding stale
`.env.local`; no manual frontend version editing is needed.

Windows x64 PowerShell:

```powershell
uv run --no-project --python 3.12 python scripts/corporate_release.py installer --manual --target windows-x64
```

Apple Silicon Mac:

```sh
uv run --no-project --python 3.12 python scripts/corporate_release.py installer --manual --target macos-arm64
```

Intel Mac: same command with `--target macos-x64`. This helper uses native
builds; it does not cross-compile Windows installers from a Mac or an Intel
installer from ARM. No containers are built in this step.

**Check:** files are under `release/installers/`, named
`OSII-0.1.1-windows-x64.exe`, `OSII-0.1.1-macos-arm64.dmg`, and
`OSII-0.1.1-macos-x64.dmg`. The helper checks Windows Authenticode or Mac
notarization stapling before copying the artifact.

Transfer those files and, for full/Core, the two Python artifacts to the same
paths on the publishing machine using your approved internal transfer method.
Compare SHA-256 before/after: `Get-FileHash PATH -Algorithm SHA256` on Windows,
`shasum -a 256 PATH` on Mac, `sha256sum PATH` on Linux. Do not transfer
private signing keys with the installers.

**If it fails:** do not rename an unsigned build as a signed release. If signing
is not ready, offer the pull-only Compose route for that platform, or obtain
an explicit IT-approved pilot process outside this signed-installer workflow.

## 6. Stage and upload the GitLab Release manually

**Where:** the publishing machine with Podman/Skopeo, all chosen artifacts,
and authenticated `glab`. The tag must already exist in corporate GitLab.

Stage all three signed targets:

```text
uv run --no-project --python 3.12 --with PyYAML python scripts/corporate_release.py bundle --manual
```

If, for example, you have only Windows x64 and Apple Silicon signing/build
machines, explicitly use this **instead**:

```text
uv run --no-project --python 3.12 --with PyYAML python scripts/corporate_release.py bundle --manual --targets windows-x64 macos-arm64
```

If no signing identities are ready, `--targets none` stages a clearly labelled
**container-only pilot**, not a finished signed-desktop release. Users follow
the Compose instructions. Do not promise an installer that is not attached.

This re-verifies all six multi-architecture images, stages only this version's
artifacts into `release/0.1.1/`, and labels missing installer targets in
`RELEASE-NOTES.md`. It generates `deployment.zip` (pull-only Compose,
non-secret `.env.example`, and instructions), `images.json`,
`python-package.json`, and `SHA256SUMS`. **It uploads nothing.**
Keep the staged notes file unchanged after checksums are made; record
acceptance results in the GitLab Release description.

For full/Core only, publish the two artifacts to the internal **PyPI** registry
as a separate step. Set up your workstation's non-secret `.pypirc` once with
repository name `osii-internal` and the project URL supplied by IT, as described
in [Python publication](corporate-deployment.md#internal-python-publication).
Twine prompts for approved credentials; do not use a public PyPI default:

```text
uv run --no-project --python 3.12 --with twine python -m twine upload --repository osii-internal release/0.1.1/osii-0.1.1-py3-none-any.whl release/0.1.1/osii-0.1.1.tar.gz
```

Uploading a wheel as a Release attachment alone does not publish it to PyPI.

Now create the GitLab Release and upload its assets. Confirm in GitLab that
the tag exists and this Release does not already exist. Check
`glab release create --help` includes `--no-update` and
`--use-package-registry`; obtain an approved current CLI if needed.

macOS/Linux/WSL:

```sh
glab release create v0.1.1 --no-update --name "OSII 0.1.1" --notes-file release/0.1.1/RELEASE-NOTES.md --use-package-registry release/0.1.1/*
```

Windows PowerShell (explicit expansion of native-command arguments):

```powershell
$releaseAssets = @(Get-ChildItem -File release/0.1.1 | ForEach-Object { $_.FullName })
glab release create v0.1.1 --no-update --name "OSII 0.1.1" --notes-file release/0.1.1/RELEASE-NOTES.md --use-package-registry @releaseAssets
```

These use the repository's GitLab context; check `origin` before uploading.
There is no runner or Job Token involved.
[GitLab CLI release creation](https://docs.gitlab.com/cli/release/create/)
supports attaching local files through the generic Package Registry.
Alternatively, create the Release in GitLab's UI for the existing tag, then
use `glab release upload v0.1.1 --use-package-registry ...` with the same
explicit asset list. Asset URLs in the UI are links, not a binary upload service.

**Check:** download an installer and `deployment.zip` from GitLab as a normal
user, compare checksums, and check the PyPI package exists only for full/Core.
Do not announce yet: the catalog and acceptance test remain.

**If it fails:** inspect Release and Package Registry first. A partial upload
may have created the Release already. Upload only missing, byte-identical
assets from the staged folder; do not rerun builds or overwrite existing assets.

## 7. Publish the catalog and verify the user experience

**Where:** a publishing shell with Quay read access. This does not require a
GitLab API token.

For the first-ever catalog only:

```text
uv run --no-project --python 3.12 python scripts/corporate_release.py catalog --manual --first-catalog
```

Later, clone/pull the approved catalog repository beside the OSII checkout,
then use its current file (substitute the real path):

```text
uv run --no-project --python 3.12 python scripts/corporate_release.py catalog --manual --catalog-file ../release-config/catalog.json
```

This verifies existing and new digest references and writes
`release/catalog.json`; it does not push or open a merge request.
Never use `--first-catalog` to replace an existing catalog.

In a second checkout named `../release-config` (clone the corporate catalog
repository there once), create the review branch:

```text
git -C ../release-config switch main
git -C ../release-config pull --ff-only origin main
git -C ../release-config switch -c release/osii-catalog-v0.1.1
```

Copy `release/catalog.json` to `../release-config/catalog.json`:
`cp release/catalog.json ../release-config/catalog.json` on Mac/Linux, or
`Copy-Item release/catalog.json ../release-config/catalog.json` in PowerShell.
Use the actual configured catalog path if it is not `catalog.json`. Then:

```text
git -C ../release-config diff -- catalog.json
git -C ../release-config add catalog.json
git -C ../release-config commit -m "release: approve OSII 0.1.1 catalog"
git -C ../release-config push -u origin release/osii-catalog-v0.1.1
```

For the first catalog, the new file is untracked and not shown by `git diff`;
open it in an editor for review. Open a GitLab merge request in the **catalog
project**, targeting its protected `main` branch.
Merge after review and publish through the configured read-only catalog URL.
Preserve prior Stack/tool entries so rollback remains possible.

**Check:** the launcher can refresh the URL and see/pull the new Stack. Finish
the [clean-workstation acceptance check](corporate-deployment.md#non-developer-acceptance-check)
for every advertised platform and the direct Compose path. Record results and
any missing platform in the GitLab Release description; only then announce it.

**If it fails:** fix catalog delivery/permissions or the catalog MR, not the
already published image tags. Existing launchers can use their cached catalog,
but a fresh workstation has no cache.

## Failed-tag recovery

Never move or recreate a published Git tag. A local retry uses the same clean
tag and the same inputs, not a rebuild from a modified working tree.

| Situation | Next action |
| --- | --- |
| Validation failed before any output was published | Correct workstation/configuration problems and retry. Source changes need a new tag. |
| AMD64 completed; ARM64 has not started | Run only the ARM64 command. Do not rebuild AMD64. |
| Both native builds passed; assembly has not started | Run assembly once. |
| An image build or assembly failed after it pushed some tags | Current scripts do not resume a partially completed image phase. Reserve that version; fix the cause and prepare a new full version. |
| Image set is complete; installer/package build failed locally | Retry only that local build from unchanged source. No image rebuild is needed. |
| GitLab asset upload failed | Inspect what exists; upload only missing identical staged files. If bytes/source must change, make a new version. |
| Release exists; catalog missing/broken | Repair the catalog branch/MR or its served URL. Do not rebuild the release. |
| `:latest` only partially promoted | Use immutable releases; fix access and repeat the same promotion. |

Inspect all six Quay repositories for `X.Y.Z-amd64`, `X.Y.Z-arm64`, and
`X.Y.Z`; also inspect GitLab Releases and Python/generic packages.
Authentication/network errors mean “unknown,” not “unused.”

If prepared/tagged `v0.1.1` failed partway through image publishing, the
replacement is `0.1.2`, **full**, with `--previous-tag v0.1.1`. That preserves
plan lineage but copies no failed artifacts:

```text
uv run --no-project --python 3.12 python scripts/release_plan.py prepare --version 0.1.2 --scope full --previous-tag v0.1.1 --dry-run
```

Start a new preparation branch from updated `main`, fix/test, run that
command without `--dry-run`, and repeat the merge/tag procedure. If the
candidate was never tagged, fix the untagged preparation branch rather than
creating an obsolete tag just to satisfy lineage.

## Promote latest

**When:** an immutable release has passed acceptance and a maintainer has
approved making it the optional corporate Quay alias.

**Before:** use its clean tagged checkout and corporate TOML; log in to Podman
and Skopeo. Record the approving person and immutable version in the Release.

**Do:** on one publishing machine:

```text
uv run --no-project --python 3.12 python scripts/corporate_release.py promote-latest --manual --approved
```

**Check:** the helper verifies both architectures and digest equality for all
six aliases. It builds nothing. Approval is your manual record, not enforced
by a GitLab protected-environment job in this mode.

**If it fails:** keep using immutable versions and rerun this promotion only.
A partially updated alias never changes pinned launchers or deployment bundles.

## Rollback

**When:** a new release fails. **Before:** identify a known-good version and back
up library/configuration data. Image rollback cannot undo a data migration.

**Do:** in the launcher stop the library, select the prior approved Stack,
pull it if needed, and restart. If the launcher itself regressed, install the
previous signed installer too. In direct Compose, retain the same deployment
directory/project, restore the prior `OSII_IMAGE_TAG` in `.env`, then
`podman compose pull` and `podman compose up -d --no-build --pull never`.
For source development, check out the prior tag in a clean checkout and restart
`make dev` or the PowerShell equivalent; back up data first.

**Check:** health, document visibility, one search, stop/restart.
**If it fails:** stop OSII and restore a compatible backup using the approved
incident procedure. Never use `down -v` or delete `.osii` as a rollback.

## Import public changes

**When:** bring public work into corporate GitLab, not the reverse.
**Before:** corporate checkout, clean tree, `public` remote or approved bundle.

```text
git switch main
git pull --ff-only origin main
git fetch public main
git switch -c import/public-YYYY-MM-DD
git merge --no-ff public/main
git push -u origin import/public-YYYY-MM-DD
```

**Check:** preserve corporate TOML and trust/mirror configuration; review the
import MR with local test evidence while runners are unavailable. Merge before
preparing a release. **If it fails:** resolve the import branch; never reset
corporate `main` to public `main`. See the
[offline bundle alternative](corporate-deployment.md#bring-public-changes-into-the-corporate-repository).
