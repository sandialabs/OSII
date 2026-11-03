# OSII hosted service feasibility and implementation plan

Prepared 5 October 2026. Proposed scope: an internal government corporate
service on OpenShift, using Microsoft 365 identities and a curated fixed
dataset, with user supplied data considered as a later phase.

**OSII is a feasible candidate for an internal hosted pilot, but the current
stack needs application authentication, authorization, user state, and shared
storage hardening before it can serve corporate users.** Its existing Core,
dashboard, worker, and processor boundaries support the transition. The largest
uncertainty is safe concurrent operation of the filesystem store and SQLite
databases, rather than container deployment itself.

The confirmed first phase gives ordinary users browsing, search, and chat;
curators manage shared changes. Start with one curated library whose assigned
users may all see the same content, with source inspection subject to data owner
permission. Disable ordinary user uploads. Preserve the local and
desktop paths while adding a hosted deployment profile to the same codebase.
Use temporary implementation branches; avoid a permanent hosted fork.

## Current direction (3 November 2026)

The active repository now supports host startup through `make dev` while
product work targets one shared OpenShift deployment, one model endpoint, and
one shared database. The workstation launcher and deployment alternatives are
preserved on `archive/workstation-deployment-2026-11-03`. References below to
retaining desktop delivery and existing container build files are historical
planning context; database consolidation and hosted access are future work.

## Feasibility and scope

| Capability | Assessment | Required work |
| --- | --- | --- |
| Internal browser service on OpenShift | Feasible | Deployment manifests, persistent storage, probes, resource limits, corporate certificates, and arbitrary UID validation. |
| Microsoft 365 sign in | Feasible through Microsoft Entra ID | Approved app registration, tenant specific OIDC integration, sessions, and corporate access policies. |
| OSII user accounts | Feasible | Profiles linked to Entra identities, account status, roles, audit attribution, and session revocation. |
| Fixed dataset shared by authorized users | Best first scope | Curator controlled publication and server enforced permissions. |
| Private collections and saved work | Feasible as an increment | Explicit ownership, separate user state, authorization on every operation, and retention rules. Current collections are shared library objects. |
| User supplied files | Feasible after isolation work | Workspace boundaries, quarantine, scanning, quotas, lifecycle management, and scoped retrieval. Existing upload support is insufficient. |
| Multiple API replicas and high availability | Requires further design | Replace or isolate SQLite operational state, coordinate canonical writes, and manage consistent index versions. |
| Mixed access restrictions inside one corpus | Substantial added scope | Permissions must constrain retrieval, previews, citations, summaries, artifacts, and exports. Prefer separate libraries initially. |

This is a deployment and product engineering assessment, not a claim that
OSII or OpenShift is authorized for a particular government data category.
The data owner and security team must establish the permitted environment,
users, model services, and handling requirements before loading that category.

### Planning assumptions

The initial pilot assumes tens of named users, roughly 5 to 10 simultaneous
active users, one curated dataset, and a supportable maintenance window.
These are sizing assumptions, not measured OSII capacity. Dataset bytes,
document counts, extracted text volume, tables, and embedding counts remain
inputs to a benchmark. Model inference uses an approved internal service;
search and extractive answers remain available when an AI model is unavailable.

Personal collections, persisted chat history, user enrichment jobs, SharePoint
synchronization, public access, and mixed classification data are outside the
minimum pilot. User accounts do not require all of those features. A fixed
dataset means originals are controlled; users can still ask questions and
inspect the existing products.

## Current architecture and gaps

The following implementation details determine the work:

| Current evidence | Hosting implication |
| --- | --- |
| Core application (`osii-core/osii/main.py`) registers API routers without a global authentication dependency or session middleware. | Protect every user route in Core. Network placement and login screens alone cannot enforce authorization. |
| Dashboard proxy (`osii-dashboard/dashboard/nginx.conf`) serves the UI and proxies `/api/` and `/artifact/` to Core on the same origin. | Keep one HTTPS origin; extend proxy routing for authentication callbacks and session endpoints. |
| Catalog (`osii-core/osii/domain/catalog_db.py`) uses SQLite WAL; job state (`osii-core/osii/domain/processing/jobs.py`) uses a second SQLite database. | API and worker storage placement matters. Do not share these databases across nodes on an arbitrary network filesystem. |
| The worker (`osii-core/osii/worker.py`) has durable queue claims and heartbeats. | Reuse existing jobs for the pilot. Atomic job claiming does not establish concurrency safety for every artifact write. |
| Collections (`osii-core/osii/domain/scopes/collections.py`) are canonical descriptors and membership files, with catalog reconciliation. They have no user ownership boundary. | Existing collections belong to the library. Private collections need a separate explicit user model. |
| Upload intake (`osii-core/osii/api/intake_routes.py`) writes files to one configured upload directory with a per file byte limit. | There is no per user workspace, quarantine, or quota boundary suitable for general uploads. |
| Core's `/artifact/{file_path}` allows files anywhere inside the resolved `.osii` root. | Replace broad rooted downloads with authorized artifact resolution; prevent access to operational databases and configuration. |
| Chat (`osii-core/osii/api/chat_routes.py`) receives history in the request; the dashboard keeps the conversation in component state. Some activity is stored in browser local storage. | Chat is not an existing server account history feature. Clear or partition browser state by identity and library. |
| Container images (`osii-core/Dockerfile`) use UBI and a named non root user. | Good corporate starting point; verify writable directories, PVC permissions, caches, and runtime behavior under the OpenShift assigned UID. |
| Compose (`compose.yaml`) exposes component ports and carries local development defaults. | Build explicit OpenShift configuration; expose only the browser entry point and replace development secrets and host references. |
| MCP (`osii-mcp/osii_mcp/main.py`) has static token authentication and a debug bypass, and reads the store through Core Python functions. | Leave MCP out of the pilot. Its direct store access must not bypass future user permissions. |
| [Corporate delivery](../operations/corporate-deployment.md) already separates public development from GitLab releases and Quay images. | Extend this workflow for hosted deployments. Current corporate releases are manual; runner automation is future work. |

The [architecture](../concepts/architecture.md) and portable `.osii` format
should remain intact. Core still owns canonical persistence and grounded
retrieval; processors receive bounded requests and do not mount the store.
Sensitivity labels are awareness metadata, not access controls, as described
in [sensitive data operations](../operations/sensitive-data.md).

## Authentication and user accounts

### Use the corporate Microsoft Entra tenant

Register OSII as an internal, single tenant application. Microsoft 365 users
authenticate through the organization's Entra tenant; OSII should not introduce
password registration, password resets, or a second employee directory.
Use separate registrations and callback URLs for development, test, and
production, with application assignment required and approved roles.

The tenant is tentatively understood to be GCC, but that is unconfirmed. The
identity team must confirm the tenant's cloud and discovery endpoint.
Government employment does not by itself identify the endpoint. Microsoft
documents separate global and US Government authorities, including
`login.microsoftonline.com` and `login.microsoftonline.us`; use the actual
tenant's authority and matching registration environment. Confirm GCC, GCC
High, or DoD configuration with the identity team rather than inferring it from
the organization's name. [Microsoft national cloud authentication](https://learn.microsoft.com/en-us/entra/identity-platform/authentication-national-cloud).

Apply corporate MFA, device, network, and sign in policies through Entra
Conditional Access where available and approved. OSII consumes their result;
it does not implement its own MFA. Confirm licensing and cloud availability
with the tenant administrator. [Conditional Access](https://learn.microsoft.com/en-us/entra/identity/conditional-access/overview).

### Recommended browser authentication design

Use server managed sign in and sessions in Core, behind the existing dashboard
origin. The browser redirects to Entra; Core handles the OIDC authorization
code flow, validates the response, and creates an opaque server session. Use
an established OIDC library, PKCE, state, nonce, exact registered redirects,
and protected confidential client credentials. [Authorization code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow).

Store the session identifier in a Secure, HttpOnly cookie with an appropriate
SameSite policy. Keep provider tokens and credentials on the server. Include
CSRF protection for state changing requests, session rotation after login,
idle and absolute expiry, and logout that invalidates the OSII session. Route
authentication endpoints through the same origin. Handle API authentication
failures as structured 401 responses so clients can prompt sign in reliably.

This design fits same origin JSON calls, PDF previews, downloads, and uploads
without adding browser bearer token storage. If the corporation already has an
approved OIDC gateway, it can replace the sign in implementation only if Core
receives a verifiable principal, untrusted identity headers are stripped, and
the API cannot be reached around that gateway. Core still enforces permissions.
OpenShift cluster administrator login is a separate concern from OSII end user
authentication.

Future script or agent access should use a separate API token design. Core must
validate access token signatures, issuer, intended audience, lifetime, and
required permissions; a Microsoft Graph token is not an OSII API credential.
Browser sessions and bearer tokens should have explicit, separately tested
validation paths. [Microsoft access token validation](https://learn.microsoft.com/en-us/entra/identity-platform/access-tokens).

### Accounts and lifecycle

Create a local OSII account record only after successful sign in and access
assignment. Key it by the validated Entra tenant ID and object ID (`tid`,
`oid`); email and display name are mutable presentation fields. This supports
stable ownership and audit attribution. [Microsoft identity claims](https://learn.microsoft.com/en-us/entra/identity-platform/id-token-claims-reference).

Minimum account state comprises identity key, display fields, enabled status,
created and last login times, effective permissions, and session revocation
state. Use an approved PostgreSQL service for accounts and server sessions if
available. Keep these tables separate from the rebuildable corpus catalog.
If a managed database is unavailable, a dedicated local SQLite account/session
store can support the same single pod pilot, with backups and migrations; that
choice blocks independent API replication until migrated.

Assign Entra application roles to approved users or groups. Confirm the
tenant's group assignment licensing and membership behavior; group assignment
requires P1 or P2 and does not cascade through nested groups. App roles reduce
the need to query Graph for general directory membership. [App roles](https://learn.microsoft.com/en-us/entra/identity-platform/howto-add-app-roles-in-apps),
[assignment and licensing](https://learn.microsoft.com/en-us/entra/identity/enterprise-apps/assign-user-or-group-access-portal).

Onboarding means granting assignment, then creating the OSII profile on first
authorized login. Offboarding means removing assignment, disabling local access,
and revoking all OSII sessions. Role changes do not automatically invalidate
existing sessions or issued tokens. Set a bounded permission refresh interval
and provide immediate local suspension for urgent removal. Establish an owner
and procedure for synchronizing removals; test the agreed revocation deadline.

## Permissions and the first user experience

| Proposed role | Allowed actions | Restrictions |
| --- | --- | --- |
| Reader | Browse the published library, inspect approved sources/artifacts, search, and chat within that library. | No uploads, processing submissions, shared edits, deletion, package imports, or service configuration. |
| Curator | Manage dataset versions and shared collections, run approved processing, review outputs, and publish updates. | No arbitrary processor/model URLs or infrastructure credentials. Destructive actions require explicit permission and existing impact confirmation. |
| Service administrator | Manage account suspension, service configuration, approved processor connections, and operations. | This role does not automatically grant access to every future restricted library. Platform privileges remain separately administered. |

Treat roles as explicit permission bundles; do not assume they form an automatic
hierarchy. Source download and package export are separate permissions to be
agreed with the data owner. Restrict exports by default in the initial pilot.
Keep administrator setup pages and curator tools out of the reader navigation.
Server checks remain authoritative even if a user directly calls an endpoint.
Limit unauthenticated exceptions to sign in/callback handling and minimal
platform health responses; protect or disable API documentation in hosted mode.

Implement a central principal and permission check at the HTTP boundary and
pass explicit authorized library/scope information into Core operations.
Audit all routers, including preview, source, artifacts, bulk summaries,
enrichments, job logs, exports, and administrative diagnostics. Every new
endpoint must be denied unless assigned a permission. A reader's `POST /api/chat`
is allowed, so blocking all POST requests is not a valid read policy.

All pilot users must be entitled to the entire published library. Folder and
collection scopes filter a query; they are not security boundaries. If that
assumption is false, introduce separate authorized libraries before the pilot
or implement permissions before any retrieval, aggregation, or model prompt.
Filtering citations after generating an answer cannot prevent information leaks.

Restrict filesystem paths to mounted roots, bind artifact downloads to approved
resources, and exclude state/configuration files. Apply safe content types,
attachment or sandbox policies for active document content, and an appropriate
Content Security Policy. User selected processor endpoints can initiate server
requests; permit only centrally approved services and restrict outbound access.

## OpenShift deployment design

The minimum topology keeps API and worker together for SQLite storage safety:

```text
Corporate browser
       |
       v
Internal HTTPS Route
       |
       v
Dashboard and same origin proxy
       |
       v
One Core pod: API container + worker container
       |              |
       |              +--> private processor Services --> approved model service
       |
       +--> curated source volume mounted read only
       +--> block backed PVC for .osii and operational SQLite state
       +--> approved account/session database

Entra <--> browser sign in and Core OIDC callbacks
Central logs and metrics <--- application and platform events
```

Use a single replica for the Core pod and a replacement strategy that prevents
old and new writers overlapping, initially `Recreate`. The API and worker share
one filesystem on one node, while retaining their separate commands and
responsibilities. Dashboard and stateless processors can use separate
Deployments. This is a bounded availability pilot: restarts, storage reattachment,
and upgrades may interrupt service. A disruption budget cannot create another
healthy replica.

### Storage and concurrency

Use a supported CSI block backed volume formatted as a local filesystem for
SQLite, with verified permissions and locking behavior. SQLite WAL requires
processes on the same host and does not work over a network filesystem. A PVC's
access mode alone does not prove its suitability; do not put the live catalog
on an NFS/RWX share. [SQLite WAL constraints](https://sqlite.org/wal.html).

Keep original sources on an approved read only mount or stage a reviewed copy
into managed storage. Preserve stable relative paths, source identity, hashes,
and dataset version so citations remain reproducible. Avoid a service account
that can read an unrestricted enterprise share. `.osii` content may contain
the same sensitive information as the originals and needs equivalent protection.

One pod still has multiple processes. Add a cross process mutation coordinator
or serialize corpus mutations through the worker. Atomic individual file
replacement does not make multi file operations transactional. Audit API paths
that currently write directly, catalog rebuilds, index replacement, deletion,
collection edits, and run state updates. Prebuild indexes before opening the
pilot; audit read paths for lazy writes and prevent uncoordinated rebuilds.

For the minimum pilot, publish corpus changes during a maintenance window:
finish active work, stop new queries/writes as needed, back up state, apply the
reviewed dataset update, rebuild required indexes, validate, and reopen access.
Reader browsing and chat must not mutate canonical corpus content. Later, staged
dataset versions and an atomic version switch can reduce maintenance time.

### Platform resources and hardening

Prepare reviewed Deployments, Services, Route, PVCs, ConfigMaps, Secrets, service
accounts, resource limits, probes, and NetworkPolicies using the corporate
platform's standard manifest or Helm/Kustomize workflow. Keep environment
overlays distinct from application source. No generic Compose conversion should
be treated as a complete production deployment.

Validate API, dashboard, processors, and bridge images under the installed
OpenShift security constraints. Support assigned numeric UIDs, permitted group
access on writable directories, non privileged ports, writable temporary/cache
mounts, no privilege escalation, dropped capabilities, and read only container
roots where practical. Keep the approved immutable RHEL/UBI base and artifact
mirrors. Do not solve permissions by granting broad `anyuid` or privileged
access. [Red Hat image guidance](https://docs.redhat.com/en/documentation/openshift_container_platform/4.20/html/images/creating-images).

Expose only the internal HTTPS entry point. Use approved TLS termination and
backend encryption for the permitted data category. Restrict ingress and egress
to required application paths, DNS, Entra endpoints, account database, telemetry,
and approved model services. Ordinary NetworkPolicy does not express a portable
DNS hostname allowlist; use the platform's approved egress mechanism for external
destinations. [Red Hat network policies](https://docs.redhat.com/en/documentation/openshift_container_platform/4.20/html/network_security/network-policy).

Remove development bridge/MCP tokens and `host.containers.internal` model
references. Supply production secrets from the approved secret manager or
OpenShift Secrets with restricted RBAC and platform encryption controls; disable
local dashboard credential writes. Configuration flags alone are not role
checks. Mount corporate trust and validate outbound TLS. Never mount Podman or
the host runtime into the application; hosted service changes go through
platform operations rather than launcher/supervisor controls.

Add startup and readiness checks for mounted storage, usable catalog, supported
schema, and account/session dependencies. The current `/health` is only a
process response. Report worker and model capability separately: model failure
should not remove browsing/search when those features remain usable. Set Route
and client timeouts to measured chat duration and bound request size, history,
retrieval depth, and per user concurrency.

## Operating and managing the service

| Responsibility | Accountable owner | Routine work |
| --- | --- | --- |
| Product and service | Named OSII service owner | Scope, access approval process, support expectations, prioritization, and funding. |
| Application | OSII maintainers | Permissions, upgrades, migrations, dependency fixes, regression checks, and incident diagnosis. |
| Platform | OpenShift operations | Projects, storage, routing, certificates, backups, cluster policies, monitoring, and deployment execution. |
| Identity | Entra administrators | Registrations, assignments, Conditional Access, credential rotation, and removals. |
| Data | Dataset owner and curators | Approved sources, membership, markings, versions, quality, retention, and publication. |
| Security | Corporate security and authorization team | Applicable controls, review, vulnerability handling, audit/incident procedures, and authorization decisions. |

Assign actual people and backup owners before production. Begin with published
business hours support and scheduled maintenance unless a funded availability
requirement demands more. Put support contacts, current dataset version, and
available model capabilities in the user interface.

Operate development, test, and production in separate projects with separate
credentials and storage. Test with permitted representative data. Record each
deployment's application version, image digests, configuration revision, dataset
version, processor versions, and model/embedding version. Upgrade test first,
then promote the same approved artifacts into production.

Export structured logs and metrics centrally. Audit access denials, account
changes, source/download/export access, dataset publication, processing jobs,
destructive actions, and configuration changes. Include actor, resource,
dataset version, outcome, and correlation ID. Treat prompts, retrieved text,
answers, and filenames according to their sensitivity; do not log full content
or tokens by default. Establish audit retention with the responsible team.

Monitor latency/errors, storage and inode use, worker heartbeats, queue depth,
database locks, failed jobs, model availability, quota consumption, certificate
and credential expiry, and backup failures. Rate limit expensive chat and
processing per user as well as globally.

Back up originals or their authoritative source reference, canonical sidecars,
governance and shared collections, account state, necessary job state, and
configuration. Indexes are rebuildable; user state and canonical annotations
cannot be replaced by an index rebuild. Quiesce writers or use a consistent
SQLite backup and filesystem snapshot procedure; copying live database files
alone is inadequate. Restore into an isolated environment and prove both data
and permissions before relying on backups.

Propose a pilot recovery point objective of 24 hours and recovery time objective
of one business day, subject to data owner approval and a timed restore test.
Keep security suspension, model outage, storage full, failed reindex, rollback,
credential rotation, and account removal runbooks. Schema and corpus format
changes may require restoring compatible state as well as the previous image.

## Data publication and future uploads

### Fixed dataset publication

The data owner approves one versioned corpus manifest: included files, hashes,
provenance, handling rules, permitted audience, and source/download permissions.
Curators ingest it in test, inspect extraction and representative citations,
and validate search before publishing. Users see a dataset version and update
date. Source revisions enter a new reviewed publication; user actions do not
silently redefine the reference corpus.

Use only approved model providers for that content. Keep provider credentials
server side and restrict processors to bounded inputs. Establish whether prompts
and outputs are retained or used by the provider and where processing occurs.
Documents are evidence, not trusted instructions: retrieved text must not cause
unapproved tool execution or endpoint changes. Preserve extractive fallback
and clearly identify the provider used and grounding citations.

### Options for user supplied data

| Option | Feasibility and tradeoff |
| --- | --- |
| Users submit files for curator approval into the common library | Smallest expansion. Quarantine and review precede publication; the submitter accepts that published content is shared with the library audience. |
| Private or project workspaces alongside the fixed library | Recommended eventual user data model. Separate owned originals, sidecars, indexes, quotas, membership, and retention. Queries combine only explicitly authorized libraries. |
| Dedicated OSII instance for each project or user | Strong practical separation with less shared authorization logic, but greater pod/storage/support overhead. Consider project instances for a small number of sensitive groups. |
| All users upload into one common directory and index | Unsuitable for private data. Filename randomization and a UI filter do not provide isolation. |

Before enabling private uploads, bind every document, artifact, collection,
index, job, and download to a workspace selected from the authenticated user's
permissions. Derive ownership on the server; do not trust a supplied owner ID
or path. Retrieval, context assembly, citations, scope summaries, previews,
job logs, exports, and cached answers must all enforce the same boundary.
Include workspace and dataset version in cache keys. Never deduplicate by
revealing another workspace's file existence or content.

Accept uploads into isolated quarantine storage with file and request limits,
workspace quotas, validated types, malware scanning, and archive expansion
limits. Run approved parsers in constrained processors with time/memory limits
and minimal network access. Release clean, accepted files to immutable original
storage and queue processing under the workspace identity. Object storage is a
possible later backend, but current path based Core workflows need an explicit
storage adapter; adding a bucket alone does not provide compatibility.

Define deletion, export, retention, ownership transfer, and project closure,
including derived text, embeddings, aggregate products, caches, and backups.
Backup expiry follows the approved retention schedule and any applicable hold.
User requested deletion must not promise immediate erasure from retained backups.

SharePoint/OneDrive ingestion is a separate integration. It needs approved
Graph permissions, cloud correct endpoints, and a deliberate ACL/revocation
strategy. Signing in with Microsoft 365 neither mounts a user's drive nor
grants access to their files. Defer this integration until upload/workspace
isolation is established.

## Branch and release strategy

**Use branches for implementation and review; keep hosted and local behavior
in the shared product.** Begin an implementation branch such as
`feature/hosted-service-foundation`, then use smaller branches for identity,
permissions, and deployment changes. These are suggested names; this assessment
does not require changing the current branch.

Keep reusable authentication interfaces, account ownership, permission checks,
and OpenShift compatible image changes in the portable codebase. A local
deployment may use an explicit local principal. Hosted configuration must fail
startup if identity settings are absent and must never fall back to anonymous
access. Test both deployment modes.

Keep actual tenant IDs, internal URLs, trust bundles, policy settings, manifests
with corporate values, and release credentials in the corporate configuration
layer or its approved private deployment repository. Preserve GitLab as corporate
release authority and Quay as image registry. Import public changes through
reviewed import branches as already documented in
[corporate delivery](../operations/corporate-deployment.md).

Promote reviewed immutable image digests and deployment/configuration revisions
through test and production. Do not deploy directly from a developer branch or
mutable `latest`. Record approvals and evidence in GitLab; until runners exist,
use a reviewed manual build and promotion procedure. Hosted releases need the
relevant images and manifests, while desktop releases retain their existing
launcher validation path. Avoid making launcher installation a server release
prerequisite when desktop components have not changed.

## Phased implementation and acceptance

The following effort ranges are engineering estimates for one experienced
developer with part time platform/identity support. They assume the minimum
reader/curator scope, an available OpenShift project, and an approved model
service. They are not elapsed delivery commitments; identity provisioning,
security authorization, procurement, and staffing can dominate the schedule.

| Phase | Work and deliverables | Indicative engineering effort | Exit condition |
| --- | --- | --- | --- |
| 0 Environment and scope | Confirm tenant/cloud, data audience, user actions, model policy, cluster version, storage class, database, owners, and recovery targets. Benchmark representative local corpus. | 3 to 5 days | Agreed pilot scope and feasible platform/identity/storage prerequisites. |
| 1 Identity and accounts | OIDC/session integration, Entra roles, account store, suspension/revocation, reader UI, and account aware browser state. | 2 to 3 weeks | Assigned users sign in; unassigned/wrong tenant users fail; removed users lose access within the agreed bound. |
| 2 Permissions and storage | Complete route inventory and permission enforcement, bounded artifacts, mutation coordination, curated dataset publication, and concurrency checks. | 2 to 3 weeks | Readers cannot mutate or access admin/state files; concurrency/restart tests preserve corpus consistency. |
| 3 OpenShift pilot | Manifests, arbitrary UID fixes, TLS/trust/secrets, restricted networking, probes, telemetry, backup/restore, and operating runbooks. | 2 to 3 weeks | Deployment meets installed cluster policy; representative restore and rollback succeed; load goals are met. |
| 4 User evaluation and release | Pilot cohort, relevance/citation review, performance tuning, operating handover, and corporate release review. | 1 to 2 weeks | Service/data/platform owners accept results and the support plan. |
| 5 Private saved work | Owned collections/bookmarks and optional retained conversations outside shared corpus state. | 1 to 3 additional weeks | Cross user authorization, retention, and browser/account switching checks pass. |
| 6 User supplied data | Choose submission or workspace model, then implement quarantine, quotas, isolation, scoped retrieval, and lifecycle rules. | Curated submission: 2 to 4 weeks; private workspaces: 6 to 10 or more weeks | Full isolation and scanning acceptance tests pass before user uploads open. |

Allow roughly **8 to 12 engineering weeks for the minimum hosted pilot**, then
reestimate after phase 0. Phases may overlap with appropriate staffing, but
identity and permissions precede access to real corporate data. Private uploads
and continuous high availability are additional projects, not a switch in the
pilot configuration.

### Required verification

1. Identity tests reject wrong tenant, invalid callback state/nonce, expired
   sessions, unassigned users, and forged principals. Logout, account suspension,
   role changes, and urgent access removal meet the agreed deadline. If bearer
   access is added, reject tokens for other audiences and insufficient scopes.
2. A route permission matrix tests every reader and curator action through
   direct HTTP calls, including alternate routes and bulk operations. Artifact,
   preview, source, export, job/log, and configuration paths obey the same policy.
   Include CSRF and account switching/browser cache checks.
3. Simultaneous browsing/search/chat, curator operations, worker restarts,
   index replacement, full storage, and interrupted jobs leave coherent state.
   SQLite queue recovery tests alone are insufficient.
4. Deploy under the actual cluster security policy and verify volume permissions,
   TLS/trust, readiness, secrets, network restrictions, absence of externally
   reachable component ports, and approved build inputs.
5. Restore a complete library plus accounts into test; verify source hashes,
   representative citations, access rules, and recovery duration. Rehearse rollback
   with compatible schema/corpus state.
6. Benchmark the agreed dataset and active user count. Suggested pilot targets
   are search p95 under 2 seconds and non model browse calls p95 under 1 second;
   agree a separate chat target after measuring the approved provider. Run
   combined workload long enough to expose lock contention and memory growth.
7. Before private uploads, two adversarial workspaces cannot discover each
   other's IDs, metadata, snippets, summaries, artifacts, jobs, citations, exports,
   or cached answers; rejected/quarantined files never enter retrieval.

### Capacity and ongoing cost

Budget for API memory/index residency, processor CPU/memory, original and sidecar
storage, backups, account database, model usage, and ongoing support. A starting
test reservation could be 2 to 4 vCPUs and 8 to 16 GiB for the API, with separate
worker/processor requests based on representative extraction. These are trial
allocations, not production sizing; document complexity can change them greatly.
GPU capacity belongs to the model service unless OSII explicitly hosts inference.

Estimate storage from measured originals, canonical sidecars, indexes, operational
state, one staged corpus version, and the backup retention factor, with working
space and headroom. Track per query model usage and per document processing time.
An existing OpenShift cluster does not eliminate database, storage, model,
security review, patching, and operator effort. Prepare a cost estimate using
internal rates after the benchmark and platform consultation.

## Decisions for the corporate team

Resolve these during phase 0, recording the owner and decision in GitLab:

- Which Entra tenant/cloud, app registration process, role assignment model,
  conditional access requirements, and session revocation deadline apply?
- What data category and audience are approved, and may every pilot user see
  every document? Are source downloads and package exports allowed?
- The agreed first phase allows ordinary users to browse/search/chat while
  curators manage shared changes. Confirm whether later phases need private
  collections, retained conversations, or user processing jobs.
- What are the actual corpus size, formats, update cadence, active user count,
  latency goal, maintenance tolerance, and support hours?
- Which OpenShift version, storage class, account database, egress mechanism,
  secret manager, monitoring, backup, and release process are available?
- Which model/embedding services are approved for the data, with what limits,
  retention behavior, and capacity? Is extractive operation acceptable initially?
- Who owns the service, data, identity integration, operations, security review,
  and funding? Which authorization process is required before broader use?
- For later uploads, is the goal curator submissions, private workspaces, or
  project libraries? How will sharing, retention, and project closure work?

Proceed to implementation when the identity route is approved, all pilot users
share an allowed data audience, compatible storage is available, and named
owners accept the bounded availability/support model. If block backed storage
or planned downtime is unacceptable, move operational state and corpus write
coordination into the foundation phase and revise the estimate before committing
to production.
