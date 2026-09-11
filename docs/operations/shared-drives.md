# Shared drives and Samba

OSII works with files on SMB/Samba shares after the operating system has made
the share available as a normal folder. This keeps network authentication in
Windows, macOS, Linux, or an approved credential manager—not in OSII, `.env`,
`.osii`, browser storage, logs, or container configuration.

OSII does not modify originals. A share may be read-only. Extracted text,
catalogs, indexes, processing history, uploads, and enrichments go into a
separate writable runtime directory on the workstation.

## Windows

Connect the share in Windows first. Then use a mapped drive:

```powershell
.\scripts\osii.ps1 dev-shared `
  -SourceDir "S:\Team Documents"
```

Or use its UNC path directly:

```powershell
.\scripts\osii.ps1 dev-shared `
  -SourceDir '\\server\share\Team Documents'
```

Choose a distinct local artifact location when desired:

```powershell
.\scripts\osii.ps1 dev-shared `
  -SourceDir '\\server\share\Team Documents' `
  -RuntimeDir "D:\OSII\team-documents"
```

Run OSII as the same Windows user who can open the share. Drive letters mapped
only in another account or elevated/non-elevated session may not be visible;
the UNC path is usually less ambiguous. OSII reports an unavailable or
unreadable share before starting the application.

## macOS and Linux

Mount or connect the share through the operating system first. Then pass its
mounted folder:

```bash
make dev-shared SHARED_DRIVE_PATH="/Volumes/Team Documents"
```

```bash
make dev-shared \
  SHARED_DRIVE_PATH="/mnt/team-documents" \
  SHARED_DRIVE_DATA="./osii-data/team-documents"
```

Do not put a Samba username or password in these commands. The first path is
the already connected source; the second is ordinary local OSII state.

## What the dashboard shows

Intake displays:

- whether the source is local or shared;
- the exact documents root OSII is allowed to browse;
- whether the source is currently readable or read-only;
- the separate `.osii` artifact location and whether it is writable.

If a share disconnects while OSII is running, Intake becomes unavailable for
new processing and explains which source needs attention. Existing canonical
artifacts remain local and usable after the source reconnects. Use **Rescan
source paths** if files were reorganized on the share.

## Packaged Podman deployment

The host share must already be mounted and visible to Podman. Start the normal
packaged stack with that host path:

```bash
make run-shared SHARED_DRIVE_PATH="/mnt/team-documents"
```

```powershell
.\scripts\osii.ps1 run-shared -SourceDir '\\server\share\Team Documents'
```

Compose mounts the source read-only at `/data/source`; canonical `.osii` state
stays in the managed `osii-data` volume. On macOS and Windows, Podman runs in a
Linux virtual machine, so the chosen host folder must also be shared with that
machine. When that is difficult, use the bare-metal `dev-shared` workflow—it
does not add a second filesystem boundary.

OSII does not start a Samba server, mount a remote share, or accept share
credentials. Managed deployments should mount shares through their platform
and expose only the intended document root to the OSII containers.

## Current scope

One running OSII process has one active documents root. Different shares can
use different local runtime directories without moving either originals or
artifacts, but switching between several live Libraries in one dashboard is a
separate multi-Library feature. This shared-drive workflow establishes the
safe path and storage behavior that feature will use.
