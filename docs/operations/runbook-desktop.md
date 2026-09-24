# Desktop launcher runbooks

These are the normal paths for people who do not develop OSII. Use a *signed,
immutable corporate release*, not a source checkout or `:latest`.

The maintainer may publish the GitLab Release manually; installation is the
same with or without CI runners. Choose the installer for your OS and CPU.
If your platform has no signed installer yet, use the
[pull-only container instructions](runbook-development.md#use-published-containers-without-building).

## Mac launcher

**When:** Use an approved OSII release on a Mac, including Apple Silicon or Intel.

**Before:** IT provides Podman Desktop, a working Compose provider, corporate
certificates, Quay access, and the signed `.dmg` matching your Mac. Connect a
shared drive in Finder first if your originals are on a share.

**Do:** Install the `.dmg` from the corporate GitLab Release. Open **OSII
Launcher**, sign in to Quay when the approved images are not already local,
refresh the approved catalog, and choose a complete **OSII Stack release**.
Pull its three Stack images. Then choose the document folder, click **Test
container access**, save the library, and select **Start OSII**. Open the
dashboard from the launcher. Optional Toolbox images are separate catalog
choices; add only the ones you need. Configure a model connection later in
Workbench **Setup**; model keys do not belong in the launcher.

**Check:** The launcher reports Core and dashboard healthy. In the dashboard,
ingest one small document and complete one search. Stop and restart OSII once;
the library must still be present.

**If it fails:** Read the catalog warning and activity output first. A cached
catalog may be used during a temporary catalog outage, but the launcher never
discovers releases by enumerating Quay tags. Use the deployment preview/logs
for startup failures. A port already in use may belong to a different launcher
profile, so stop that profile in the launcher. For Ollama on the Mac, a container connection uses
`http://host.containers.internal:11434`, not `127.0.0.1`. See
[model connections](../reference/model-providers.md).

## Windows launcher

**When:** Use an approved OSII release on a Windows workstation.

**Before:** IT provides Podman Desktop, Compose, corporate certificates, Quay
access, and the signed Windows `.exe`. Open a shared drive in Explorer first;
OSII does not save share credentials.

**Do:** Run the installer from the corporate GitLab Release. Open **OSII
Launcher**, sign in to Quay when needed, refresh the approved catalog, choose a
complete **OSII Stack release**, and pull its three Stack images. Choose the
source folder, click **Test container access**, save the library, and select
**Start OSII**. Open the dashboard from the launcher. Optional Toolbox images
are separate catalog choices. Configure any model connection in Workbench
**Setup**.

**Check:** Core and dashboard show healthy. Ingest one small document, search
for its content, then stop and restart OSII without losing the library.

**If it fails:** Read the catalog warning and activity output, then use the
deployment preview/logs and check Podman Desktop. A temporary catalog outage
can use the last valid cached catalog; do not substitute an unreviewed Quay
tag. Do not run an unrelated `make down` or delete containers by guessing
their names; launcher profiles use separate Compose projects. See
[shared-drive access](shared-drives.md) or [corporate setup](corporate-deployment.md).

## Update or roll back an existing installation

**When:** the maintainer announces an approved release.

**Before:** back up your library/configuration and read the release notes.
Keep the existing saved library profile and source folder; do not create a
new library just to update its images.

**Do:** for a Stack update, stop OSII in its saved profile, refresh the catalog,
select the approved Stack and explicitly pull its images, then restart.
Select/pull optional tools separately when their versions change. **Start does
not pull images.** For a launcher fix, quit the launcher and install the new
signed installer for your platform from GitLab, then reopen your existing
profile. There is no automatic installer updater in this procedure.

**Check:** process/search one file, then stop/restart; check saved connections
and library contents. Confirm the new launcher version if you installed it.

**If it fails:** stop OSII and select/pull the prior approved Stack. For a
launcher regression also reinstall the previous signed installer. Keep logs
and data; image rollback does not reverse a storage migration. See
[rollback](runbook-releases.md#rollback).
