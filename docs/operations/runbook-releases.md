# Release runbooks

Corporate GitLab is the release authority. These steps are **not yet turnkey**:
the Linux AMD64/ARM64, Windows, and macOS runners and signing credentials must
be provisioned and the pipeline exercised before an automated release is
called operational. See [one-time setup](corporate-deployment.md#configure-gitlab-once).

## Import public changes

**When:** Bring approved public GitHub work into corporate GitLab.

**Before:** Work in a corporate checkout with a `public` remote or an approved
Git bundle. Preserve the private `corporate/osii.toml` and protected CI secrets.

**Do:** Fetch public `main`, create an import branch from corporate `main`,
merge `public/main`, resolve conflicts, and open a corporate merge request.
Use the exact [import commands](corporate-deployment.md#bring-public-changes-into-the-corporate-repository).

**Check:** GitLab validation passes; review the public diff plus corporate
adaptations. Merge to corporate `main` before preparing a release.

**If it fails:** Resolve conflicts on the import branch. Do not reset the
corporate checkout to public `main` or copy internal defaults to GitHub.

## Full corporate release

**When:** Make the first release, update an approved base or shared build
input, or deliberately rebuild all images.

**Before:** Merge source and configuration to corporate `main`; confirm all
five runner classes, signing, approved mirrors, and Quay credentials are ready.
Keep secrets in protected GitLab variables. For one-time non-secret defaults,
see [corporate configuration](corporate-deployment.md#corporate-defaults).

**Do:** On a release-preparation branch, run the command below, review its
version edits, commit, and merge the branch. Then create a protected tag
`vX.Y.Z` on that merged commit in GitLab and approve `approve-release`.

```bash
uv run --no-project --python 3.12 python scripts/release_plan.py prepare --version 0.1.1 --scope full --previous-tag v0.1.0
```

Add `--dry-run` first to see the planned work without editing files. After
preparing and merging, run `uv run --no-project --python 3.12 python scripts/release_plan.py check` on `main`.

**Check:** The tag pipeline verifies the release plan, builds both Linux
architectures, produces signed Windows/macOS installers, publishes the internal
Python package, and creates a GitLab Release with digests. Test the installer
on a clean Mac and Windows workstation before announcing the release.

**If it fails:** Do not reuse the tag or overwrite published image versions.
Fix the cause and prepare the next version. See [corporate delivery details](corporate-deployment.md).

## Component update

**When:** Release only a changed component while keeping one tested stack
version. Use `core`, `ui`, `launcher`, `toolbox-tesseract-opencv`,
`toolbox-tabular`, or `toolbox-llm-wikis` as the scope.

**Before:** Ensure the previous corporate release succeeded. A Core/SDK change
also rebuilds every Python image and publishes a new `osii` package. UI-only
rebuilds only the dashboard; launcher-only rebuilds no containers. Every stack
release still produces a new installer with the new pinned version.

**Do:** On a release-preparation branch, substitute the actual next version,
scope, and prior tag:

```bash
uv run --no-project --python 3.12 python scripts/release_plan.py prepare --version 0.1.1 --scope ui --previous-tag v0.1.0
```

Add `--dry-run` first to validate the proposed scope without editing files.

Commit and merge the preparation change. On merged `main`, run
`uv run --no-project --python 3.12 python scripts/release_plan.py check`; then create the matching protected
GitLab tag and approve the release. The pipeline rejects changes outside the selected
scope and copies unchanged images by verified digest to the new stack tag.

**Check:** The GitLab Release lists the new stack version, reused Python
package version when applicable, and all six AMD64/ARM64 image digests. Test
the changed behavior and the clean-workstation launcher path.

**If it fails:** Do not broaden the scope inside a running tag pipeline. If
the diff touched shared build inputs, prepare a *new* full release version.
The first corporate release after introducing these release scripts must be
`full`, because shared build machinery changed since `v0.1.0`.

## Promote latest

**When:** Offer the most recently approved release under corporate Quay's
moving `:latest` alias. This is optional and never a launcher default.

**Before:** The immutable GitLab Release and clean-workstation acceptance
checks must already pass. Only a release maintainer should have permission to
use the protected `corporate-promotion` environment.

**Do:** Open that release's GitLab tag pipeline and run the separate manual
`promote-latest` job. It copies each verified multi-architecture image; it does
not build anything.

**Check:** The job verifies that every `:latest` manifest has Linux AMD64 and
ARM64 and matches the approved release digest. Record the promoted immutable
version in the release notes.

**If it fails:** Keep using the immutable version. A partially moved alias is
not a deployment target; rerun the idempotent promotion job after correcting
registry access. Never rebuild directly into `:latest`.

## Rollback

**When:** A newly deployed release fails acceptance or operation.

**Before:** Identify the last known-good immutable release and back up the
library. Check whether the new version changed persisted formats; image
rollback alone cannot reverse a data migration.

**Do:** In the launcher, edit the library profile's image tag to the prior
approved version, then stop and start OSII. For direct Compose, put the prior
`OSII_IMAGE_TAG` in its local `.env`, then use the normal pull/start command.

**Check:** Core and dashboard are healthy; open the existing library and
complete one search. Confirm the version actually running.

**If it fails:** Stop OSII, preserve logs and library data, and restore the
tested backup under the approved incident procedure. Do not delete `.osii`
or reuse a release tag.
