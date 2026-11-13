# OSII server deployment and recovery

`main` is standalone; `osii-server` is the PostgreSQL application. Use separate
worktrees and ignored configuration. Transfer portable fixes deliberately.
Never migrate or rewrite the other branch's data implicitly.

## Local development startup

After database migration and administrator bootstrap, use `make dev` (Windows:
`scripts/osii.ps1 dev`). Setting `OSII_DEV_POSTGRES_DIR` in the ignored `.env`
opts into starting an existing local cluster; no cluster is initialized and no
schema/account changes are made by startup. `DATABASE_URL` must use a loopback
host, and selects the port. Already-running clusters are reused after checking
their port and readiness. A missing cluster, mismatched tools, or startup failure
stops the launcher before it starts application services. PostgreSQL stays running
on Ctrl+C; its log is `postgres.log` beside the configured cluster directory.

The current Mac uses `/opt/homebrew/opt/postgresql@18/bin`, cluster directory
`osii-data/postgres`, and port `55432`. Set `OSII_DEV_POSTGRES_BIN` if discovery
cannot find the matching tools. Omit both dev variables for externally managed
PostgreSQL. They are never needed by the OpenShift workloads.

For development checks, set `TEST_DATABASE_URL` to an isolated PostgreSQL
database ending in `_test`, then run `make test`. Tests recreate that database's
public schema; never use the application database. The command runs Core/SDK
tests and the dashboard tests and build.

## Headless use and retrieval evaluation

Install `osii[server]`, provide deployment configuration, and run
`uvicorn osii.server.api:create_app --factory`. Run ingestion separately with
`python -m osii.server.worker`. Node, the dashboard, MCP, and optional processors
are not required to serve an already-ingested corpus.

API clients call `/api/auth/login`, retain the session cookie, and send the
returned `csrf_token` in `X-CSRF-Token` for writes. `/api/capabilities` describes
supported workflows. OpenAPI documentation requires an administrator session.
`/health` checks the process and `/ready` checks database/schema readiness.

Search combines BM25, Unicode/numeric-aware normalization, bounded
character-similarity expansion, and optional compatible semantic vectors. Source
text and offsets remain unchanged by search. Private uploads, saved private
conversations, Microsoft SSO, legacy package/editing workflows, and filesystem
MCP are outside this server's supported workflows.

To evaluate real OCR, prepare an ignored JSONL file containing `query` and
`expected_sources` (relative source paths) per line. Use 30–50 labelled cases:

```bash
uv run --env-file .env --package osii --extra server python -m osii.server.evaluate osii-data/queries.jsonl
```

The evaluator reports source Recall@k and MRR. Semantic/hybrid modes require
`--allow-paid-embeddings`. Synthetic regression tests do not establish quality
on the real corpus.

## Images and configuration

Build the hosted Core and dashboard Dockerfiles from the repository root. All
authored stages use shared `OSII_BASE_IMAGE`. Public development may use UBI 9;
published images must use an approved immutable base digest. Supply approved
mirrors and the `osii_ca_bundle` build secret for corporate trust. Do not change
distribution if an approved dependency is unavailable. Core dependencies are
hash-pinned in `osii-core/requirements-server.txt`, exported from `uv.lock`.

```bash
podman build --build-arg OSII_BASE_IMAGE="$OSII_BASE_IMAGE" -f osii-core/Dockerfile -t "$CORE_IMAGE" .
podman build --build-arg OSII_BASE_IMAGE="$OSII_BASE_IMAGE" -f osii-dashboard/dashboard/Dockerfile -t "$DASHBOARD_IMAGE" .
```

Publish reviewed images through the approved workflow and supply their digests
to OpenShift. `.dockerignore` excludes originals, runtime databases, secrets,
environments, notebooks, and frontend dependency trees. Supply an approved RHEL
PostgreSQL 15+ image as `DATABASE_IMAGE`. Verify image pulls, target architecture,
assigned UID, writable temporary mounts, and native runtime dependencies before
promotion. The current local integration tests run PostgreSQL 18.

## OpenShift resources

### Build application images in the cluster

`deploy/openshift/build.yaml` creates two binary Docker builds and ImageStreams
in the selected project. The existing Dockerfiles retain the pinned UBI base;
builds run on the cluster's architecture and publish to its internal registry.
The project must allow Docker builds and internal-registry pushes. No application
Secret or source dataset belongs in a build input.

From a clean, committed server worktree, select the project and prepare a small
archive of tracked application files. This excludes ignored `.env`, credentials,
originals, local databases, dependency directories, and Git history. Inspect the
archive before uploading; tracked files are still the operator's responsibility.

```bash
oc project heidikmkv-dev
OSII_REVISION=$(git rev-parse HEAD)
OSII_IMAGE_TAG=$(git rev-parse --short=12 HEAD)
git archive --format=tar --output=osii-data/openshift-source.tar "$OSII_REVISION" \
  osii-core osii-dashboard/dashboard deploy/openshift/nginx.conf .dockerignore
tar -tf osii-data/openshift-source.tar
oc process --local -f deploy/openshift/build.yaml \
  -p IMAGE_TAG="$OSII_IMAGE_TAG" -p SOURCE_REVISION="$OSII_REVISION" | oc apply -f -
oc start-build osii-core --from-archive=osii-data/openshift-source.tar --follow --wait
oc start-build osii-dashboard --from-archive=osii-data/openshift-source.tar --follow --wait
oc get builds
oc get istag "osii-core:$OSII_IMAGE_TAG" "osii-dashboard:$OSII_IMAGE_TAG"
```

Binary builds require an explicit upload for each release; automatic triggers
are disabled. Each build requests 500m CPU/512 MiB and permits up to 2 CPU/2 GiB.
Check both builds are `Complete`, inspect their image architecture, and select
the resulting image digests before deployment. Record the source revision and
digests with the release. Never deploy a failed or still-running build tag.

### Deploy the application

`deploy/openshift/template.yaml` defines separate API, worker, extractor,
dashboard, and database workloads. The database uses a block-backed PVC. API
and worker mount a shared source PVC read-only; processors have neither source
mounts nor database credentials. Storage defaults `gp3` and `efs-sc` match the
inspected sandbox and must be selected explicitly elsewhere. Aggregate initial
requests are 1.6 CPU and approximately 5.6 GiB memory.

Create Secrets without putting values in shell arguments or Git:

- `osii-database`: keys `username`, `password`, `database`, and `url`. Prepare an
  owner-only ignored env file and use
  `oc create secret generic osii-database --from-env-file=PATH`. The URL is
  `postgresql+psycopg://USER:ENCODED_PASSWORD@osii-database:5432/DATABASE`.
- `osii-model`: file key `key`, created using
  `oc create secret generic osii-model --from-file=key=PATH_TO_PRIVATE_KEY_FILE`.

Choose an HTTPS hostname under the cluster's allowed domain, then inspect and
apply the rendered resources:

```bash
oc process --local -f deploy/openshift/template.yaml \
  -p CORE_IMAGE="$CORE_IMAGE" -p DASHBOARD_IMAGE="$DASHBOARD_IMAGE" \
  -p DATABASE_IMAGE="$DATABASE_IMAGE" -p APP_HOST="$APP_HOST" > /tmp/osii-resources.json
oc apply --dry-run=server -f /tmp/osii-resources.json
oc apply -f /tmp/osii-resources.json
```

API/worker startup fails closed until migration completes. After the database
is ready, run the migration Job with the same Core image:

```bash
oc process --local -f deploy/openshift/migrate.yaml -p CORE_IMAGE="$CORE_IMAGE" | oc apply -f -
oc wait --for=condition=complete --timeout=300s job/osii-migrate
oc logs job/osii-migrate
oc rollout restart deployment/osii-api deployment/osii-worker
oc rollout status deployment/osii-api --timeout=180s
```

Use a unique `JOB_NAME` for subsequent migrations. Do not add schema creation
to startup. Bootstrap interactively with:

```bash
oc exec -it deployment/osii-api -- python3.12 -m osii.server.cli bootstrap-admin --username admin
```

Enter the password at its hidden prompt. Bootstrap is only available when there
are no accounts. Administrators create other users and deliver temporary
passwords through an approved channel. Users change those on first login.

Only the dashboard has an external Route. Its HTTPS origin must exactly match
`OSII_ORIGINS`. Never enable `OSII_INSECURE_LOCAL_HTTP` in OpenShift. Browser
sessions are HttpOnly/Secure, use CSRF protection, expire after 30 minutes idle
or 12 hours total, and are revoked by password/role/account changes. Chat budgets
are enforced per user (10 requests/15 minutes) and globally (100/15 minutes) in
the database. Searches that may request embeddings have separate per-user
(20/15 minutes) and global (200/15 minutes) limits. Lexical search remains
available when those limits are reached. The provider key's spending cap is
the hard monetary limit; request limits do not predict dollar cost.

Network policies restrict ingress and egress; extractors have no outbound
connections. Core API/worker may contact public HTTPS model endpoints. Corporate
deployment must restrict that further using the approved egress mechanism.
The developer template uses edge TLS for public test data; corporate backend
encryption, certificates, and authorization require the corporate policy.

## Dataset publication and verification

Populate the source PVC through a separate administrator staging Job that mounts
it writable. Do not grant source-write access to API/worker. Retain a source
manifest with hashes and dataset version outside the sandbox. In Administration,
discover models, save exact IDs, and explicitly test invocation. Catalog listing
is not a generation or billing test. Provider keys are deployment Secrets.
Changing the embedding model requires reprocessing the documents. Administrators
manage accounts and model selections; curators ingest and manage collections;
readers browse, search, and chat.

Curators process the fixed directory. Configure a bounded OCR extractor through
`OSII_OCR_URL` for image-only files; native text extraction does not perform OCR.
Inspect source pages, text, citations, and job results before retrieval evaluation.
The worker commits each document and its embeddings together. A failed file is
logged with its relative path and a sanitized reason; processing continues with
the next file. Processing logs are saved before and after each document and are
available through Processing or the curator-only `GET /api/runs` endpoint while
the job runs. The final summary gives processed, unchanged, and failed counts.
A completed scan with failed files has status `error`; this does not roll back
successful documents. A database outage or worker shutdown stops the batch.
After correcting the cause, choose **Process shared dataset** to retry: matching
committed documents are skipped. **Reprocess all documents** deliberately repeats
successful extraction and embedding calls too.

Embedding requests retry network failures and HTTP 408, 429, 500, 502, 503, and
504 up to three attempts, with exponential delay and numeric `Retry-After`
capped at 30 seconds. Permanent failures are reported without repeated requests.
Lost responses can still incur provider charges. Processor timeouts are not
automatically retried because the processor may still be working. PDF extraction
can contain NUL characters, which PostgreSQL cannot store. Before chunking, Core
replaces each with U+FFFD, preserving character offsets, and records the count in
document metadata under `normalization`. The stored extraction response uses the
same normalized values; source PDFs are never changed.

A changed original returns 409 on preview until re-ingestion, preventing a new
PDF from being shown as evidence for old extracted content.

Verify `/ready`, source previews, search, chat, and a separate reader login.
Readers have no Setup, Processing, or Administration controls; direct forbidden
API calls must return 403. Do not expose the filesystem MCP adapter or unported
legacy routes. Conversations remain temporary. Collections are private by default; curators
and administrators manage published shared collections. No private uploads, public registration, or Microsoft SSO is enabled.

## Hosted library administration and collections

Local and hosted products use the same workbench header, responsive sidebar,
spacing and file-card grid. The Library group exposes Files (the default flat
view), Browse (folders), Search, Chat and Collections. Topic explorer is under
Tools. Administrators additionally see Add files, Setup and Users. Readers and
curators do not receive shared-dataset processing or configuration controls. These are authenticated Core clients, not separate filesystem/database
interfaces. All corpus operations remain available through the Core API.

**Setup → Source folder** shows the deployment's `OSII_SOURCE_DIR`, selected relative
folder, availability/readability, indexed document/chunk/embedding counts, and
model/extractor configuration. Its source browser lists originals before they
have been processed. It hides dotfiles and symbolic links, returns 200 entries
per page, and caps directory browsing at 20,000 entries. Files are never uploaded,
modified, or deleted by this browser. Reading file names does not mean they have
been extracted or embedded.

**Setup** groups model connections, source selection and processing methods.
Its numbered readiness panel distinguishes saved model selections from service
verification: model sample tests run only on demand. Text and semantic coverage
come from PostgreSQL counts; semantic coverage requires every chunk of a document
to have a nonempty vector for the selected model. Readiness counts are cached by
dataset revision and selected embedding model. Intake and re-embedding invalidate
them; simultaneous refreshes share one aggregation. Source availability is still
checked live. The cache contains only derived counts and is rebuildable. Opening Setup never calls a model.
Old `#source`, `#models` and `#processors` bookmarks still open the corresponding
Setup section, with the same account checks.

**Add files** opens Intake. Add files chooses mounted sources; Process library
starts with the work to perform (embeddings, summaries, extraction, enrichment
or custom), then document selection and processing options. Preview freezes the
batch before staging; staging never starts work. Activity retains the explicit
start, pause, resume, cancel and retry controls. Source files remain read-only.

Administrators can select a subfolder inside the mounted root using
`PUT /api/admin/source` with `{"directory":"relative/subfolder"}`. The selection
is stored in PostgreSQL. Absolute paths and paths outside that mount are refused.
Changing the mount itself remains an operator/deployment task. On the current
Droplet, host `/mnt/nfs-documents` maps read-only to application `/data/source`.

The setting affects future Processing requests only. Each queued ingestion job
captures its `source_directory`; changing the selection does not redirect queued
jobs or remove previously indexed documents or collections. Source identities
and preview paths stay relative to the mounted root, even when processing only a
subfolder. Pre-upgrade jobs without the new field retain the original root scope.
Moving/removing originals can make old previews unavailable; source hashes still
prevent serving a replacement as evidence for the old extraction.

Any reader can select individual documents in Library, search results, or Topic
explorer, then create a private collection or add them to a collection they manage.
Collections can be renamed, described, and deleted; members can be removed without
removing source documents. Browse, search, chat, and topics share a scope selector.
A private collection belongs to its creator and is absent from other users' API
results, including administrators. This privacy concerns saved membership and
metadata; the underlying fixed dataset remains shared. It is not a document ACL
or protection against a database operator. Curators/administrators may publish
their own collections and manage shared collections; only the owner can turn a
shared collection private. Other users' private collections are not exposed to
curators for review. Concurrent edits that race a privacy change are rejected.

Migration `0002_workspace` preserves existing collections as shared, adds nullable
ownership for those legacy rows, and makes new collections private by default.
Names are unique per owner. Apply it explicitly before starting the matching API
and worker. Downgrade is intentionally refused: restore a compatible backup for
rollback rather than risk publishing private work.

Topic explorer uses the selected embedding model's stored PostgreSQL chunk
vectors. It normalizes chunks, averages each document's vectors, normalizes again,
and projects the document vectors with deterministic PCA (an approximate,
bounded subspace fit for larger datasets). It makes no provider
calls, stores no secondary corpus, and does not use FAISS or `.osii` directories.
The interactive map includes every currently indexed document in the selected
scope; related ranking uses cosine similarity across the same full scope. All
points are drawn on a canvas, with viewport-dependent thumbnail and label detail.
Exploration allows up to 8,192 dimensions and a 64 MiB float32 document-vector
matrix (about 10,922 documents at 1,536 dimensions). The memory guard returns an
error rather than sampling a subset. A mixed dimension index is refused. Missing and stale model vectors are reported;
selecting another embedding model requires processing to populate compatible
vectors. The map is experimental: 2D proximity is approximate, not evidence of a
factual relationship or an automatically inferred topic label.

## Backup and recovery

### Wake an idled Developer Sandbox

Developer Sandbox is a trial environment, not continuous hosting. Red Hat lists
a 30-day trial and a 12-hour consecutive pod runtime limit in its
[Sandbox FAQ](https://developers.redhat.com/developer-sandbox/FAQ). The Sandbox
operator can scale Deployments and StatefulSets to zero. A Route can still exist
and return HTTP 503 because no dashboard pod is running. This is independent of
the CLI login token expiring. Inspect actual workloads after authenticating:

```bash
oc login --web --server=https://api.rm2.thpm.p1.openshiftapps.com:6443
oc get deployment,statefulset,pods,pvc -n heidikmkv-dev
```

If the workloads have zero replicas and their PVCs remain bound, start the
database first, then the application. Restarting a Deployment alone does not
change a desired replica count of zero.

```bash
oc scale statefulset/osii-database --replicas=1 -n heidikmkv-dev
oc rollout status statefulset/osii-database -n heidikmkv-dev --timeout=120s
oc scale deployment/osii-api deployment/osii-worker deployment/osii-extractor deployment/osii-dashboard --replicas=1 -n heidikmkv-dev
oc rollout status deployment/osii-api -n heidikmkv-dev --timeout=120s
oc rollout status deployment/osii-dashboard -n heidikmkv-dev --timeout=120s
```

Verify the HTTPS dashboard, anonymous API rejection, schema readiness, and
stored accounts/data. Do not rerun bootstrap, recreate Secrets, delete PVCs,
or rebuild images just to wake an idled instance. PVC persistence survives pod
replacement; it does not replace backups or extend the trial. Arrange a
longer-lived OpenShift project for an always-on example.

### Minimal independent deployment exercise

This exercise reuses the already-built UBI Core image but overrides its command
to run Python's small HTTP server against `/tmp`. It does not start Core, connect
to PostgreSQL, mount source files, or use the provider key. It teaches the three
basic pieces: a Deployment runs the process, a Service gives it an internal
address, and a Route gives it an external HTTPS address.

```bash
oc project heidikmkv-dev
OSII_TEST_IMAGE=$(oc get deployment osii-api -o jsonpath='{.spec.template.spec.containers[0].image}')
oc create deployment osii-smoke --image="$OSII_TEST_IMAGE" -- python3.12 -m http.server 8080 --directory /tmp
oc expose deployment osii-smoke --port=8080
oc create route edge osii-smoke --service=osii-smoke --insecure-policy=Redirect
oc rollout status deployment/osii-smoke --timeout=120s
oc get route osii-smoke
```

Open `https://` followed by the Route's hostname. A directory-listing page is
the expected result; this is a disposable HTTP exercise, not an OSII instance.
Inspect it with `oc get pods` and `oc logs deployment/osii-smoke`. Remove only
these exercise resources when finished:

```bash
oc delete route,service,deployment osii-smoke
```

### Database backup and restore

Back up PostgreSQL with `pg_dump` and retain matching originals/source manifest
and deployment configuration. Keep backups outside the disposable sandbox,
encrypted under the permitted handling policy. Provider keys are restored from
the secret manager separately. No search-index files are required.

Restore with `pg_restore` into an isolated database, mount matching originals
read-only, restore configuration/secret references, and verify schema readiness,
login, roles, source hashes, known queries, and citations. API caches rebuild
from database records. Time this restore before relying on the service.

Pause writers for coordinated dataset changes. Run migrations explicitly before
matching application images. Incompatible schema rollback requires a compatible
database backup as well as the previous image; changing the image alone does not
undo migrations. Trial expiry, model failure, or missing storage must never cause
a fallback to an empty filesystem store.

## Inventory and library-wide tools

Administrators can open **File inventory**, or use the same location browser
inside **Add files**. Register a directory beneath the configured source mount,
start a metadata scan, and watch its directory checkpoints and issues. Scanning
reads directory entries and stat metadata only: it does not hash sources, extract
text, build embeddings, or call a model. Sources remain read-only. Pause, resume,
cancel, and retry use the durable worker queue. A disconnected or incomplete
folder never provides evidence that its unseen files were deleted. Rebinding a
changed mount is explicit and invalidates old selections without deleting history.

Filter the inventory or take a reproducible stratified sample, then freeze a
batch. Coverage and source revisions are retained with that batch. Incomplete
coverage requires explicit acceptance. **Review frozen batch in Intake** opens
its exact members for preview, exclusion and staging; processing still requires
**Start processing**. Plans accept at most 5,000 files. Source identity, metadata
and inventory revisions are checked again at processing boundaries. Inventory
observations are distinct from processed documents; scanning an existing corpus
does not itself mark every document as newly processed or replace its evidence.

**All tools** and **Library at a glance** reuse the local scope picker, action
panel, product views and overview. Administrators run configured synthesizers or
enrichers over a library, folder, collection or document. Built-in source-excerpt
synthesis and statistics/keywords need no model service. Other tools advertise
their scopes through their Processor SDK descriptor. Connect optional running
services in **Setup → Processors**; the Core does not install or start Toolbox
services. Per-document extraction and embedding stay in Intake.

Hosted scope tools freeze every selected document's full usable saved text into
bounded PostgreSQL batch rows. There is no 1,000-document limit or per-document
prefix sampling. Requests contain at most 32 text windows and 100,000 characters,
with smaller configured tool/window budgets respected. Long documents span
multiple requests. Pause, cancel and retry operate between calls; completed
batches and built-in synthesizer model-call checkpoints survive restarts.

The run report shows document, text-character and batch progress, including
files without usable text. Its paginated details preserve original text ranges
and every batch result. Model-backed wiki methods combine summaries
hierarchically. Other tools retain partitioned results unless they explicitly
opt into wiki reduction. Batch-local rankings are labelled accordingly. Local
frequency keywords combine complete batch counts before global ranking; sampled
phrase clues are examples from batches, not a global ranking.

Model-backed methods can consume credit for each text and reduction batch.
Nothing is automatically queued on upgrade. Frozen full-text inputs/results are
retained operational evidence; allow database and backup capacity for them.

Readers can inspect visible products; curators and administrators can edit them.
Private collection visibility is enforced on products, revision history and run
inspection. Concurrent edits use expected revisions. A new generated result
becomes a review candidate when a human edit is current. Activating a revision
records an editorial event. Source text and original files are unchanged.

This feature requires the explicit `0005_scope_batches` PostgreSQL migration
before starting matching API and worker images. Back up the database first and
use the existing migrate CLI; startup does not run migrations. Inventory tables
and scoped product histories are canonical records, not rebuildable caches. The
downgrade refuses to discard them; restore a compatible backup for rollback.


### Workbench landing page

Home (`/`) presents six document tools; Files (`/files`) retains the flat library.
Analyze Library opens the overview, whose **All tools** link opens the processor
workbench. Search supports lexical retrieval without embeddings. Chat and report
tiles require saved text and a configured AI model; Topic Explorer requires
current compatible embeddings and can explore a partially indexed library.
Gray tools show what is missing. A configured model is not a connection test.

Setup appears until **Done with setup** is saved for this library. Hosted Setup
is administrator-only. It remains accessible in the sidebar after dismissal.
`GET /api/workbench/home` supplies metadata-only readiness;
`POST /api/admin/setup/dismiss` persists dismissal (administrator and CSRF checks
apply on the hosted service). Home does not read source text, load vector payloads,
compute projections, or invoke models. Shared tile/navigation definitions and
UI components consume product adapters; they do not access storage directly.


### Droplet proxy after API replacement

The Droplet dashboard mounts `/etc/osii/dashboard-nginx.conf`, rendered by
`deploy/droplet/configure.py` from the shared OpenShift template. It uses the
validated private Podman DNS server (`10.89.0.1`) and a variable API upstream
with a five-second DNS validity period. Paths, query strings, request bodies,
authentication cookies, and the existing security headers are preserved.
This avoids retaining an obsolete container address after an API-only rollout.
The OpenShift template continues to target its stable Service address.

Check the public `/api/auth/me` after deployment: an anonymous request must
return JSON HTTP 401, not HTTP 502 or HTML. A successful static Home page alone
is insufficient. If an older deployment retains an obsolete API address,
restart **only** `osii-dashboard` to restore it, then install the rendered
Droplet configuration. Workers and OCR services need no restart.

See the [NGINX proxy documentation](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass)
for variable upstream resolution.

### Hosted tool lifecycle boundary

**Setup → Service status** reuses the local service-row presentation through an
administrator-only API. The Droplet deployment can opt into a private Unix-socket
controller for its explicitly deployed extractor/OCR units; see the
[Droplet service controls](runbook-droplet.md#hosted-service-status-and-lifecycle-controls).
Missing controllers fail closed. No shell, arbitrary service/unit name, provider
key, or container-engine socket is exposed to the dashboard or Core. Stop/restart
can interrupt an extraction; pause Intake before using them. OpenShift lifecycle
control requires a separate deployment adapter and is not implicitly enabled.

### Hosted document pages and text corrections

Files open at `/files/{file_id}` as full document pages. Files uses compact cards
without Text/Synth status badges; Browse owns its single explorer heading.
In Split View the PDF is on the left and Grounded Text is on the right.
**Text options** beside Grounded Text expands the extraction-representation
selector. Historical extractions remain read-only and selecting one does not
change the preferred search representation.

Administrators and curators can **Edit Text**, **Save**, or **Restore** with the
shared segment editor. PostgreSQL retains immutable extraction evidence and
human edit history; the mounted source file is never written. Saved edits become
preferred text, refresh lexical chunks immediately, and discard obsolete vectors.
Rebuild embeddings for semantic retrieval. Derived outputs display stale status
until they match current preferred text. Revision checks reject concurrent edits
and extraction changes with HTTP 409; failed saves keep the editor draft.
Readers can view corrections but cannot save or restore shared text. Hosted
writes require CSRF protection and create audit events. These changes require no
database migration.
