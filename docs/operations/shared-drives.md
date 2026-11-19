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
.\scripts\osii.ps1 dev `
  -SourceDir "S:\Team Documents"
```

Or use its UNC path directly:

```powershell
.\scripts\osii.ps1 dev `
  -SourceDir '\\server\share\Team Documents'
```

Choose a distinct local artifact location when desired:

```powershell
.\scripts\osii.ps1 dev `
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
OSII_SOURCE_DIR="/Volumes/Team Documents" OSII_SOURCE_KIND=shared make dev
```

```bash
OSII_SOURCE_DIR="/mnt/team-documents" OSII_RUNTIME_DIR="./osii-data/team-documents" OSII_SOURCE_KIND=shared make dev
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

## Runtime storage

Keep runtime databases and indexes on local disk. OSII reads originals through
the mounted path and does not manage share credentials. Use distinct local
runtime directories for distinct source libraries. For resumable discovery and
bounded processing, follow [File inventory](large-volumes.md).
