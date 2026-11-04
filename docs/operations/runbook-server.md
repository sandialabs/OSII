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

Curators process the fixed directory. Configure a bounded OCR extractor through
`OSII_OCR_URL` for image-only files; native text extraction does not perform OCR.
Inspect source pages, text, citations, and job results before retrieval evaluation.
A changed original returns 409 on preview until re-ingestion, preventing a new
PDF from being shown as evidence for old extracted content.

Verify `/ready`, source previews, search, chat, and a separate reader login.
Readers have no Setup, Processing, or Administration controls; direct forbidden
API calls must return 403. Do not expose the filesystem MCP adapter or unported
legacy routes. Conversations remain temporary and shared collections are curator
managed. No private uploads, public registration, or Microsoft SSO is enabled.

## Backup and recovery

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
