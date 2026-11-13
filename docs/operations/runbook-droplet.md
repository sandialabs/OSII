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
PostgreSQL API responses into those view models. The library opens with a flat
view of all indexed files in the selected scope; **Folders** switches to immediate
children. Both search and the flat view include descendants. Collections remain
private by default and support selection in list and thumbnail views.

Keyword search is the default and makes no embedding request. An embedding failure
during ingestion now commits the extracted text and lexical passages, reports
`text_only` in the processing log, and marks the run as needing attention. Retry
processing after the endpoint is restored; completed compatible documents are skipped.
No embedding model is selected or invoked automatically.

Endpoint administration separates configured selections from available models.
Use **Find available models** in the Add/Change dialog before saving; model identifiers
are kept behind the name selection. It uses the same endpoint fields and model picker
as local Setup; hosted
persistence stays in Core/PostgreSQL. See [model endpoints](model-endpoints.md).
Microsoft SSO is not enabled yet. Its future OIDC identity must map to an existing
stable OSII user ID to preserve roles and private collections; matching email or
username alone is not an account-linking policy.


## Staged Intake and document inspection

As an administrator, open **Add files** (Intake). Under **Add files**, browse
mounted folders and select files or folders. **Process library** selects already
indexed documents. Choose text intake/refresh, re-extraction, or embedding-only
processing. Text-only is the default; embeddings require an explicitly selected
model and can incur provider charges. Embedding-only work reuses canonical chunks
and replaces vectors transactionally without another extraction.

Choose **Preview selected files**, review the exact list, then **Stage plan**.
Staging stores a durable, unstarted plan in PostgreSQL; it does not invoke a
processor. In **Activity**, review its files and choose **Start processing**.
The worker handles one file at a time. **Pause** and **Cancel** finish the current
file safely; **Resume** skips completed files, and **Retry** revisits failed or
unfinished files. Per-file status, timings, errors, progress and live logs use
the same activity component as local. Worker availability is based on a heartbeat,
not just a successful API response.

Plans contain at most 5,000 visible files, each at most 50 MiB. Source files stay
read-only. A changed source fails its staged item instead of silently processing
the changed file: stage a new plan to review it. A changed model/processor
configuration also requires a new plan before start/resume. Endpoint/model edits
are blocked while jobs are queued or active, including pause/cancel requests.
Staged/paused plans survive API and worker restarts. Expired leases recover active
work; an interrupted current file can be repeated, while completed checkpoints
are retained. A pause/cancel request survives lease recovery. Legacy curator
batch APIs remain compatible; the new staged-plan controls are administrator-only.

Opening a document uses the shared **Text / Source / Split View / Extractions /
Syntheses / Wiki / Enrichments** tabs. PDF.js renders the authenticated PDF in a
canvas, so the application can keep `frame-ancestors 'none'`. Extraction history
preserves Processor SDK responses and their source/OCR regions in PostgreSQL.
Selecting an older representation changes only the viewer. It does not promote
that version into search. Administrators and curators can edit preferred text on the document page; extraction promotion remains a separate future feature. The
Syntheses, Wiki and Enrichments panes show saved responses with processor/model
provenance and stale-input warnings.


## Synthesis and enrichment

Under **Add files** (Intake) → **Process library**, choose summaries, enrichment,
or a custom workflow using existing text
to derive new outputs without re-reading the source. Enable **Generate document
summaries** and/or **Run enrichment**, select methods, adjust their displayed
settings, and optionally supply expert context. You can also combine these steps
with intake, re-extraction or embeddings. Preview and stage the plan, then start
it from Activity. The same pause/resume/cancel/retry controls apply. Pause/cancel
finishes the current document, including its selected downstream steps. Completed
synthesis/enrichment steps survive a later failure and are skipped on retry.

The cited source-excerpt preview and statistics/keyword enrichment are model-free
and work immediately. **Openai Synthesizer** uses the language model selected in
Setup → Model connections and may incur provider charges. Selecting or previewing a method never
invokes it. Outputs appear in the document's Syntheses/Enrichments panes; Wiki
shows wiki-markdown enrichment products. **Stage processing for this document**
opens Intake with that file preselected. Outputs do not replace extracted text
or become search evidence automatically. Model-generated claims remain derived
content, not verified source statements.

Under **Processor connections**, add the base addresses of explicitly deployed
Processor API services, one per line. Their `/v1/descriptor` must declare
a unique processor name and one of the four SDK component kinds. Synthesis and
enrichment methods must support object scope for per-file plans. Connections are
admin-managed PostgreSQL settings; `OSII_PROCESSORS` supplies deployment defaults.
This does not launch tools, install models or copy Toolbox code into Core. The
current hosted planner runs each selected file separately; aggregate folder,
collection and root synthesis/enrichment are not yet exposed by these plans.

For model-backed remote processors, Core supplies a short-lived SDK model grant,
not a provider key. Set `OSII_PROCESSOR_GATEWAY_URL` to a Core API address reachable
from those services, ending in `/api/processor-model/v1`. The Podman and OpenShift
default is `http://osii-api:8512/api/processor-model/v1`; processors outside that
network may need `https://osii.app/api/processor-model/v1`. Grants bind exact chat/
embedding selections to an active job lease, expire after ten minutes, permit at
most 16 model requests, and are revoked when the operation ends. The gateway has
no corpus or filesystem endpoints. Keep processor services on an approved network;
Processor API service authentication is managed by that deployment.

External synthesis/enrichment requests are limited to 200,000 characters of
primary document text, configuration to 16,000 serialized characters, and each
response to 4 MiB. Built-in model synthesis uses bounded windows instead of the
200,000-character document limit. Model-free preview/keywords can read longer
canonical text without making a model request. Gateway
chat is non-streaming and limits responses to 16,000 tokens; embedding requests
allow at most 128 texts and 200,000 input characters. External methods that cannot accept a long document fail with a
clear per-file error instead of silent truncation. No schema migration is needed;
plans, checkpoints, output envelopes and temporary grant hashes use existing
PostgreSQL tables. Older staged plans may require re-staging after this adapter
upgrade; existing documents, outputs and jobs are retained.


## Optional native OCR and Toolbox health

Administrators can open **Setup → Processing methods** for descriptors, readiness,
and **Queue extraction/synthesis/enrichment** actions. Adding a URL registers
an already running Processor API service; it does not install software.
Ordinary users cannot change connections or queue shared processing.

To explicitly install the two native OCR services on this Ubuntu 24.04 host,
include `osii-processor-modules/osii-tesseract` in the immutable release archive and use
the configurator's `--with-ocr` flag. They use a separate hashed Python lockfile
and environment under `/opt/osii/tools`; Core's image and lockfile gain no OCR
dependencies. The `osii-ocr-page` service provides full-page Tesseract at private
`10.89.0.1:8193`, and `osii-ocr-regions` provides the experimental OpenCV region
extractor at private `10.89.0.1:8194`. Both run as `osii-ocr`, without access to
NFS, PostgreSQL, or deployment secrets. Keep these ports private.

Set `OSII_OCR_URL=http://10.89.0.1:8193` in the private deployment environment
and restart Core/worker to enable automatic fallback when native extraction
finds no text. Register `http://10.89.0.1:8194` in **Setup → Processing methods** for
explicit region extraction. Preserve existing custom endpoints when updating.

```bash
systemctl status osii-ocr-page osii-ocr-regions
journalctl -u osii-ocr-page -u osii-ocr-regions -n 50
curl --fail http://10.89.0.1:8193/ready
curl --fail http://10.89.0.1:8194/ready
```

For a failed scanned PDF, use **Restage failed files** in Intake Activity, or
select the source under **Add files**. Choose **Re-extract all selected files**,
then the OCR extractor, review settings, preview, stage, and start. For an
already indexed document, **Save another version** preserves the primary text,
search chunks, embeddings, and synthesis. It runs extraction alone. Open the
document's Extractions pane and representation selector to compare versions;
region OCR supplies bounding boxes in the shared PDF viewer. To search the OCR
text, re-extract with **Make primary**, then rebuild embeddings if desired.
Source PDFs always remain read-only. OCR jobs are bounded by the existing
50 MiB input limit and a ten-minute selected-extractor request timeout; split
very large scans into reviewed batches outside the source share if needed.

Topic Explorer streams database vectors rather than loading the entire index
into Python objects. Catalog browsing reads only document headers. A proxy HTML
response now produces an HTTP/service diagnostic instead of a JSON parser error;
check Core readiness and its journal when that diagnostic appears.

## Hosted service status and lifecycle controls

Administrators see **Setup → Service status** with live process state, a separate
Processor API health check, bounded recent logs, and start/stop/restart actions.
Stop and restart require confirmation because an active extraction can fail;
pause Intake and wait for the current document first. Queued work and saved
outputs are not deleted. Readers and curators cannot read service logs or control
services. Writes use session/CSRF authorization and actions are audited.

Enable explicitly with `configure.py --with-tool-control` when configuring the
Droplet. The controller is a separate systemd service, not a Core subprocess.
Only the API mounts `/run/osii-tools` and receives
`OSII_TOOL_CONTROL_SOCKET=/run/osii-tools/control.sock`. It has no public port or
container-engine socket. The host controller accepts only the three fixed units:
`osii-extractor`, `osii-ocr-page`, and `osii-ocr-regions`. It cannot manage SSH,
Core, PostgreSQL, workers, or arbitrary units. Optional missing units are shown
without lifecycle controls. Installing this controller does not start or restart
the managed tools.

The socket directory is preserved across controller restarts; systemd starts it
before the API on reboot. Logs are at most 80 entries from the last hour and
64 KiB of journal output. Common credential patterns are redacted; administrators
should still treat logs as potentially containing document text and sensitive
operational details. Raw command output is never returned for failed actions.

No controller is enabled by default on OpenShift. That deployment requires a
separate adapter with namespace-scoped permissions; the UI reports unavailable
controls while processor health remains available. External model endpoints,
remote processors, and in-process synthesizers/enrichers cannot be restarted
through the Droplet controller.
