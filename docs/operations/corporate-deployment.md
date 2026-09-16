# Public development and corporate releases

For the short action checklist, start with [What are you trying to do?](runbooks.md).
This page is the one-time setup and policy reference, not a daily runbook.

OSII has one codebase and two environments:

| Public GitHub | Corporate GitLab |
| --- | --- |
| Develop and review portable source | Add approved internal configuration |
| Run fast tests on Python 3.12 and Linux | Repeat validation on corporate runners |
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
- let GitLab CI pass and review the public commits plus corporate adaptations;
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
OSII_IMAGE_PREFIX = "quay.internal.invalid/team/osii"
OSII_BASE_IMAGE = "quay.internal.invalid/approved/ubi9@sha256:REPLACE_WITH_64_HEX_DIGEST"
OSII_TESSERACT_SOURCE_URL = "https://artifacts.internal.invalid/tesseract.tar.gz"
OSII_LEPTONICA_SOURCE_URL = "https://artifacts.internal.invalid/leptonica.tar.gz"
OSII_TESSDATA_BASE_URL = "https://artifacts.internal.invalid/tessdata"
OSII_MODEL_BASE_URL = "https://models.internal.invalid/v1"
OSII_EMBEDDING_MODEL = ""
OSII_CHAT_MODEL = ""
```

Replace the illustrative values with approved real ones. The helper rejects
unknown keys, placeholders, non-HTTPS endpoints, and unpinned base images.
Do not put API keys, Quay passwords, signing credentials, or certificate
contents in this file. CI variables override these defaults and hold secrets.
On a workstation, validate and create ignored `.env` and launcher `.env.local`
without overwriting any existing local files:

```bash
uv run --no-project --python 3.12 python scripts/corporate_config.py check --version 0.1.1
uv run --no-project --python 3.12 python scripts/corporate_config.py write --version 0.1.1
```

The example file is **never added to public GitHub**. Keep it on the corporate
branch when importing upstream changes. The public GitHub workflow fails if a
`corporate/osii.toml` is accidentally present.

## Make a corporate release

On a release-preparation branch, use `scripts/release_plan.py prepare` with the
next stack version, prior tag, and `full`, `core`, `ui`, `launcher`, or one
`toolbox-*` scope. This updates the launcher versions, and it updates the
Python package version only for Core/full releases. Commit and merge the plan
into corporate `main`. Create a protected tag on that merged commit, using
GitLab's **Repository → Tags → New tag** or these commands:

```bash
git switch main
git pull --ff-only origin main
git tag -a v0.1.1 -m "OSII 0.1.1"
git push origin v0.1.1
```

The protected tag pipeline validates the commit and pauses at
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
   digests, and SHA-256 checksums.

Tags are immutable. If a release fails after publishing, fix the code and
prepare a new version; never reuse the old tag or image version. After clean
workstation acceptance, the separate protected `promote-latest` job may move
corporate Quay's `:latest` aliases. The launcher and deployment bundles still
use immutable versions; `latest` is not a deployment rollback mechanism.

## Non-developer acceptance check

Before announcing the release, test on a workstation with no OSII checkout or
cached OSII images:

- install the matching signed OSII Launcher from the GitLab Release;
- confirm Podman Desktop and a Compose provider are available;
- open the launcher and confirm corporate Quay and version are prefilled;
- sign in to Quay, choose a readable document folder, and test container access;
- start OSII and open the dashboard;
- ingest a document and complete one search/chat workflow;
- enable OpenCV/Tesseract or Tabular only when needed, then test its descriptor
  and one real document;
- stop and restart OSII and confirm the library remains available.

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
- Use protected runners, variables, environment, `main`, and `v*` tags.
- Publish packages, signed installers, and immutable images only from a
  protected corporate tag.
- Keep one approved release available for rollback.
- Give non-developers the signed launcher from the GitLab Release rather than a
  source checkout or build instructions.

References: [GitLab PyPI registry](https://docs.gitlab.com/user/packages/pypi_repository/),
[GitLab release pipelines](https://docs.gitlab.com/user/project/releases/release_cicd_examples/),
and [GitLab workflow rules](https://docs.gitlab.com/ci/yaml/workflow/).
