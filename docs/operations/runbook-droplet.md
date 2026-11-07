# Single-server development example

This deployment runs the same UBI Core and dashboard images as OpenShift on
one Ubuntu 24.04 Droplet. PostgreSQL 16 and Caddy are host services; Core API,
worker, native extractor, and dashboard are separate Podman containers managed
by systemd. The database uses the Droplet's disk, not NFS. Application updates
do not replace the database or document share.

This is a small development example with a single host, not a highly available
deployment. Continue testing the OpenShift manifests separately. GitHub-driven
deployment is a subsequent setup step; these instructions do not enable it.

## Prepare the host

Install `podman`, `postgresql`, `caddy`, `nfs-common`, and `rsync` through the
host's Ubuntu repositories. Mount the managed NFS share persistently at
`/mnt/nfs-documents` before starting Core/worker. Transfer only a reviewed Git
archive of the application source and build the existing Dockerfiles from its
root. Exclude local environments, credentials, notebooks, and dataset contents.

```bash
podman build -f osii-core/Dockerfile -t localhost/osii-core:RELEASE .
podman build -f osii-dashboard/dashboard/Dockerfile -t localhost/osii-dashboard:RELEASE .
```

Use a Git revision for `RELEASE`. Build sequentially on a small host. Inspect
memory pressure during builds and processing; idle memory use is not a sizing
benchmark. A registry-based deployment can build elsewhere and pull these
images instead.

Install the private provider key at `/etc/osii/model-key`, owned by root. Copy
`deploy/droplet/configure.py` to the host, then run explicitly as root:

```bash
python3 configure.py --hostname osii.app --image-tag RELEASE
```

The configurator creates a private container network, an application database
role/database, root-only configuration under `/etc/osii`, and systemd units.
PostgreSQL listens on loopback; only API/worker receive its Unix socket and
credentials. Extractor/dashboard receive no database credentials, provider key,
or source volume. Core and worker mount NFS read-only and require an actual
NFS mount before startup, preventing fallback to an empty local directory.

The script does not run migrations, bootstrap OSII accounts, or start ingestion.
Preserve `/etc/osii/database.password` and the PostgreSQL data directory on
subsequent deployments; do not rerun provisioning with a different database.

## Migrate, then start

Run the migration explicitly using the release's Core image:

```bash
podman run --rm --network none --read-only --user 1001:0 --tmpfs /tmp \
  --env-file /etc/osii/runtime.env \
  --volume /var/run/postgresql:/var/run/postgresql:ro \
  --volume /etc/osii/model-key:/run/osii-model-key:ro \
  localhost/osii-core:RELEASE python3.12 -m osii.server.cli migrate

systemd-analyze verify /etc/systemd/system/osii-*.service
systemctl enable --now osii-network osii-extractor osii-api osii-worker osii-dashboard caddy osii-backup.timer
```

Set the hostname's DNS A record to the Droplet IP. Initially use DNS-only mode
if Cloudflare manages DNS. Permit inbound HTTP/HTTPS for certificate issuance
and serving the dashboard. Preserve SSH access. Only Caddy should listen
publicly for web traffic; the dashboard binds to host loopback port 18080.
If using UFW, also allow inbound traffic from `10.89.0.0/24` on the actual
Podman bridge and routed traffic from that bridge, so container DNS and external
model calls continue to work. Recheck both after enabling the firewall.
Caddy handles certificates and HTTP-to-HTTPS redirects. Keep secure cookies
enabled and `OSII_ORIGINS` equal to the actual HTTPS origin.

After HTTPS and backend readiness are verified, bootstrap the host's own
administrator interactively from a terminal:

```bash
podman exec -it osii-api python3.12 -m osii.server.cli bootstrap-admin --username heidikmkv
```

Sign in, select/test models in Administration, and create reader/curator
accounts as needed. Wait until source uploads have finished before requesting
ingestion. The worker does not scan automatically on startup.

## Operate and recover

```bash
systemctl status osii-api osii-worker osii-extractor osii-dashboard caddy
journalctl -u osii-api -u osii-worker -n 50
podman ps
findmnt -M /mnt/nfs-documents
```

If SSH times out, use the DigitalOcean console to inspect the host before
restarting it. A restart retains the Droplet disk and managed NFS share; a
rebuild or deletion is a different operation. Do not delete storage to fix a
failed service. Re-run manual rsync uploads after recovery to copy missing or
changed files without deleting the source.

Back up PostgreSQL using `pg_dump`, keep copies outside the Droplet, and retain
the corresponding original documents. A persistent disk or NFS share alone is
not a backup. Test restore before relying on this instance. Keep the previous
application image and match schema compatibility when rolling back.

The configurator installs a daily `osii-backup.timer`, with private compressed
database dumps under `/var/backups/osii` and seven-day age retention. These local
dumps help recover from application mistakes; arrange off-host copies separately
to protect against loss of the Droplet. They do not include the NFS originals or
deployment key files. Administrator-saved endpoint keys are stored in PostgreSQL
and are therefore included in database backups; keep those dumps private. Run `systemctl start osii-backup.service` for a fresh dump
and inspect failures with `journalctl -u osii-backup.service`.

## Hosted sessions and shared UI

Sign in with **Stay signed in on this device** selected to retain the authenticated
session for up to 14 days, with a seven-day inactivity limit. Deployment operators
can set `OSII_REMEMBER_DAYS` from 1 to 30. Without this option, sessions retain the
12-hour absolute and 30-minute inactivity limits. Sign-out, password changes,
account disabling, and authorization-version changes still revoke access.
The session stays in a Secure, HttpOnly cookie; no bearer token is put in local storage.
The explicit `0003_session_policy` migration preserves existing sessions' short
idle policy. Sign in once with the new option to obtain a remembered session.

The hosted library uses the same BrowseGrid, FileCard, PDF thumbnail hook,
SearchResultCard, and search-mode selector as OSII-local. Hosted code maps
PostgreSQL API responses into those view models. Folder browsing shows immediate
children, while search scopes still include descendants. Collections remain
private by default and support selection in list and thumbnail views.

Keyword search is the default and makes no embedding request. An embedding failure
during ingestion now commits the extracted text and lexical passages, reports
`text_only` in the processing log, and marks the run as needing attention. Retry
processing after the endpoint is restored; completed compatible documents are skipped.
No embedding model is selected or invoked automatically.

Endpoint administration uses the same endpoint fields as local Setup; hosted
persistence stays in Core/PostgreSQL. See [model endpoints](model-endpoints.md).
Microsoft SSO is not enabled yet. Its future OIDC identity must map to an existing
stable OSII user ID to preserve roles and private collections; matching email or
username alone is not an account-linking policy.
