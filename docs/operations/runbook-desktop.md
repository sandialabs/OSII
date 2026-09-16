# Desktop launcher runbooks

These are the normal paths for people who do not develop OSII. Use a *signed,
immutable corporate release*, not a source checkout or `:latest`.

## Mac launcher

**When:** Use an approved OSII release on a Mac, including Apple Silicon or Intel.

**Before:** IT provides Podman Desktop, a working Compose provider, corporate
certificates, Quay access, and the signed `.dmg` matching your Mac. Connect a
shared drive in Finder first if your originals are on a share.

**Do:** Install the `.dmg` from the corporate GitLab Release. Open **OSII
Launcher**, choose the document folder and approved version, sign in to Quay,
select optional tools only if needed, click **Test container access**, then
**Start OSII**. Open the dashboard from the launcher. Add a model connection
later in Workbench **Setup**; model keys do not belong in the launcher.

**Check:** The launcher reports Core and dashboard healthy. In the dashboard,
ingest one small document and complete one search. Stop and restart OSII once;
the library must still be present.

**If it fails:** Use the launcher's deployment preview/logs. A port already in
use may belong to a different launcher profile, so stop that profile in the
launcher. For Ollama on the Mac, a container connection uses
`http://host.containers.internal:11434`, not `127.0.0.1`. See
[model connections](../reference/model-providers.md).

## Windows launcher

**When:** Use an approved OSII release on a Windows workstation.

**Before:** IT provides Podman Desktop, Compose, corporate certificates, Quay
access, and the signed Windows `.exe`. Open a shared drive in Explorer first;
OSII does not save share credentials.

**Do:** Run the installer from the corporate GitLab Release. Open **OSII
Launcher**, choose the source folder and approved version, sign in to Quay,
select optional tools, click **Test container access**, then **Start OSII**.
Open the dashboard from the launcher and configure any model connection in
Workbench **Setup**.

**Check:** Core and dashboard show healthy. Ingest one small document, search
for its content, then stop and restart OSII without losing the library.

**If it fails:** Use the launcher's deployment preview/logs and check Podman
Desktop first. Do not run an unrelated `make down` or delete containers by
guessing their names; launcher profiles use separate Compose projects. See
[shared-drive access](shared-drives.md) or [corporate setup](corporate-deployment.md).
