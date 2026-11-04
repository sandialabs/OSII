# OSII Local and OSII Server: Expanded Functional Scope

Date: 4 November 2026

Status: Technical scope specification for the expanded software

## 1. Purpose and baseline

OSII—the On-Store Intelligence Index—has expanded from a file-based information
architecture into software for preparing, exploring, searching, and using a
document library. This specification describes the additional application,
processing, integration, and hosted-service functionality in **OSII Local** and
**OSII Server**.

For this specification, the original scope is assumed to encompass the OSII
file-based architecture: stable source identities; original-file references;
extracted text and location information; provenance; root, folder, document, and
collection representations; and inspectable `.osii` files that distinguish
source evidence from derived information. Existing concepts for summaries,
enrichments, embeddings, and rebuildable indexes are treated as architectural
foundations, rather than asserted to be new additions in themselves.

The expansion is the executable functionality built around those foundations:
interactive applications, processing workflows, replaceable services, grounded
question answering, agent-assisted knowledge maintenance, and a hosted,
authenticated database-backed application. This is a functional comparison,
not a reconstruction of the wording or boundaries of an earlier approval.

The description reflects the inspected source worktrees, including uncommitted
development. “Implemented” below means an implementation is present; it does
not mean that a particular release has been published, a production deployment
accepted, or all intended operating conditions validated.

## 2. Two application forms

| Aspect | OSII Local | OSII Server |
| --- | --- | --- |
| Intended use | A standalone library operated on a workstation or within a locally controlled environment. | One shared library accessed by authenticated users through a hosted service. |
| Authoritative persistence | Portable, filesystem-backed `.osii` records; derived catalogs and search indexes support access. | PostgreSQL records for extracted content, provenance, chunks, vectors, artifacts, collections, accounts, settings, and jobs. |
| Originals | References existing source files or accepts files through local intake workflows; extraction does not edit originals. | Reads a deployment-configured dataset from a read-only source volume. |
| Interface | Browser Workbench, Core APIs, Python interfaces, and a Model Context Protocol adapter. | Role-aware browser application and authenticated HTTP APIs. |
| Access model | Local operating-environment controls; not the Server account/permission system. | Reader, curator, and administrator accounts with server-enforced permissions. |
| Current delivery | Host startup through `make dev` or the PowerShell equivalent. | Separate server branch with host development startup and OpenShift deployment resources. |

These are separate persistence implementations. Server is not simply Local
placed behind a web address. Local capabilities are not automatically exposed
by Server, and there is no implied automatic migration between their stores.

## 3. Additional OSII Local functionality

### 3.1 Interactive Workbench

The browser application turns the file architecture into a working environment
for users who do not manipulate sidecar files directly. It provides document
and folder browsing, source previews, extracted-text inspection, collection
management, search, question answering, processing controls, and configuration.
Users can move from a result or generated answer to its referenced document
and available source locations.

Document views expose extraction alternatives, derived summaries, enrichment
artifacts, labels, and other associated information. Editable text is a separate
representation; it does not redefine the original file or the character-offset
coordinates of canonical extracted evidence.

The frontend also has an extension registry for independently routed tools.
Tools consume Core APIs and use shared identities and scope definitions. They
do not directly access the store or invoke model endpoints. The registry and
topic explorer are present in current Local worktree development.

### 3.2 Controlled intake and processing

Local adds workflows for selecting existing files or folders, accepting uploads,
resolving a proposed processing scope, and previewing eligible, current, stale,
or blocked work before it is queued. Users can run extraction, summaries,
embeddings, or enrichments separately instead of repeating the entire pipeline.
Activity views expose processing progress and results.

Extraction upgrades preserve versioned outputs and allow a user to choose a
primary extraction. Promoting a different version marks dependent outputs stale
so they can be regenerated. A failed replacement extraction does not become
the primary result. This adds lifecycle management and lineage tracking beyond
the ability to store a text extraction and its provenance.

Human-supplied expert context can accompany selected documents or scopes and
be passed to a compatible processor. It is identified as guidance, not extracted
evidence. Saving guidance does not establish that a processor used it, and
changing guidance does not automatically regenerate earlier outputs.

### 3.3 Search and grounded question answering

Core implements keyword retrieval, optional vector-based semantic retrieval,
and combinations of the two. Requests can be limited to the whole library, a
folder, a collection, or a document. Search chunks retain links to source
identities and canonical text offsets rather than replacing those identities.

Question answering adds retrieval-augmented generation: Core retrieves bounded
evidence, constructs a model request, and returns an answer with source
references and information about the provider or fallback actually used.
Extractive responses can present source excerpts when generative service is
unavailable. Basic extraction and keyword search do not require a language model.

These functions organize evidence for interpretation; they do not establish
that every generated statement is true or supported by its citations. The
software does not train a foundation model as part of this workflow.

### 3.4 Derived knowledge products and library maintenance

Users can request summaries and enrichment products at supported document,
folder, collection, or library scopes. Standard outputs include Markdown wiki
pages, structured tables, keywords, entity lists, and graph-shaped artifacts
where a compatible processor supplies them. Core validates and persists the
returned artifacts and their provenance.

Local additionally supports sensitivity labels, tags, handling notes, selective
deletion workflows, and collection package export/import. Packages contain
sidecars and a checksum manifest, not original source files. Labels communicate
handling information; they do not implement encryption or access control.
Deletion and transfer require attention to related outputs and retained copies,
not just the source document's visible entry.

### 3.5 Agent-facing documentation and knowledge maintenance

The Model Context Protocol (MCP) adapter lets an external coding or research
assistant query the ingested library, inspect bounded source passages, and read
or save cited wiki pages through Core functionality.

The documentation workflow adds reuse of previously saved knowledge, metadata
for applicability such as software/version, revision conflict checks, limited
revision history, and freshness checks against source fingerprints. Changed
evidence can make a page stale. The external assistant decides when to research,
write, and revise; OSII is not independently running an autonomous research loop.

Saved pages remain derived and unreviewed. Citation validation checks locations
and scope membership, not whether the cited passage proves the written claim.
The existing filesystem-oriented MCP adapter is a Local capability and is not
part of Server's authenticated interface.

### 3.6 Topic exploration

The Local topic explorer adds a visual map and related-document navigation over
an existing compatible embedding index. Core aggregates document vectors,
projects them into two dimensions using principal component analysis, and ranks
related documents using cosine similarity in the full vector space.

The view reports index identity, coverage, staleness, and projection limitations.
It does not generate embeddings during browsing, automatically assign topic
names, or treat graphical distance as a complete measure of relatedness.
Lexical hashing is distinguished from semantic embeddings. This capability is
present in the Local working tree and has not been ported to Server.

## 4. Processor and model integration

The expanded software includes a Processor SDK and a versioned HTTP protocol
for four roles: extraction, synthesis, embedding, and enrichment. Descriptors
advertise capabilities and configuration; typed requests carry one document or
a bounded scope snapshot; typed responses return segments, vectors, or artifacts.

Core controls dispatch, validation, provenance, and persistence. A conforming
processor receives explicit inputs rather than independent authority to browse
the corpus or change its authoritative records. The protocol permits new
implementations without changing the library's fundamental information model.

Included baseline services provide native document extraction, full-page OCR,
local extractive summaries, lexical-hashing embeddings, basic statistical
enrichment, and adapters to configured model services. Optional Toolbox
implementations add region-based OpenCV/Tesseract OCR, tabular processing, and
model-generated narrative or concept/entity wikis. Their presence in the source
tree does not make them default services or establish Server integration.

Model adapters connect to separately operated inference services, including
OpenAI-compatible endpoints and, in Local, local-model services such as Ollama.
An API-compatible service need not be operated by any particular vendor.
The application selects models and sends requests; model weights, training
systems, service subscriptions, and provider infrastructure are separate inputs.

Local exposes connection settings and credential-source information in Setup.
Server uses one deployment-configured model endpoint and credential, with model
selection controlled by administrators. A model catalog listing is distinct
from successfully invoking the selected generation or embedding model.

## 5. Additional OSII Server functionality

### 5.1 Database-backed shared library

Server replaces the authoritative filesystem store with PostgreSQL while
retaining the separation of source evidence, provenance, and derived outputs.
The database holds extracted text, extraction records, source identifiers,
chunks, embeddings, artifacts, shared collections, configuration, and operational
state. Originals remain on a separately managed source volume.

Only Core API and worker components access the database. Document processing
commits related records transactionally, and corpus revisions identify changes
used to rebuild retrieval caches. Server does not fall back to SQLite or an
empty `.osii` store if its database is unavailable. Schema migrations and first
administrator creation are explicit operations.

### 5.2 Accounts, sessions, and differentiated permissions

Server introduces application-managed password accounts and sessions:

- Readers browse documents, inspect evidence, search, and ask questions.
- Curators additionally process the configured dataset and manage shared
  collections.
- Administrators additionally manage accounts and model selections.

The implementation includes password hashing, temporary-password changes,
session revocation following account/password/role changes, authenticated API
access, request-origin and cross-site request forgery checks, and recorded
administrative/access events. The browser reflects these permissions, while
the server checks permissions independently of which buttons are visible.

The current model is one shared audience for one library. It is not a
multi-tenant workspace system and does not provide private per-document access
rules, personal uploads, public registration, or enterprise single sign-on.
Accounts, session records, and audit events introduce operational user data
beyond the original document information architecture.

### 5.3 Hosted processing, retrieval, and model-use controls

A curator queues ingestion of the configured source directory. A separate
worker claims jobs using database-backed leases and heartbeats, coordinates
corpus writes, extracts text, creates chunks, optionally obtains embeddings,
and commits results. Unchanged documents can be skipped; explicit reprocessing
repeats extraction and configured model calls.

An OCR endpoint can be configured for image-only documents. An empty extraction
is reported as a failure rather than accepted as searchable content. Source
preview checks the recorded hash and rejects a changed original until it is
re-ingested, avoiding presentation of new bytes as evidence for old text.

Server retrieval combines keyword ranking, Unicode/numeric-aware normalization,
bounded character-similarity expansion for imperfect OCR, and optional compatible
semantic vectors. Normalization applies to search representations and does not
rewrite canonical evidence. Scope filtering precedes ranking. Hybrid retrieval
can report a lexical fallback; semantic-only requests require usable vectors.

Server adds shared per-user and global request limits for model-backed
operations. These limit request frequency, not monetary expenditure. Model
discovery, explicit invocation tests, and an evaluation utility support checking
exact model IDs and retrieval performance against labeled queries. The presence
of an evaluator or regression tests is not a measured accuracy claim for a
particular document collection.

### 5.4 Hosted delivery and operation

The Server worktree includes container definitions and OpenShift resources for
API, worker, extractor, dashboard, and database workloads. These specify storage,
configuration and secret references, service routing, health/readiness checks,
and network-policy boundaries. Deployment credentials and actual internal
endpoints remain environment-specific configuration.

Operating guidance covers dataset publication, explicit migrations, database
backup/restore with matching originals, and rollback compatibility. Core and
worker source mounts are read-only; processors have neither the source-volume
mount nor database credentials. Hosted delivery is an implementation under
development, not evidence of production authorization, high availability, or
completed recovery validation.

## 6. Functional availability and limits

| Capability | Local source | Server source |
| --- | --- | --- |
| Browse, inspect sources, search, grounded answers | Implemented | Implemented for authenticated shared-library use |
| Intake and processing management | Local selection/upload and multi-step workflows | Curator-triggered processing of the fixed dataset |
| Version selection, editable text, package transfer, sensitivity annotations | Implemented Local workflows | Not part of the current hosted API |
| Shared collections | Filesystem-backed collections | Database-backed, curator-managed collections |
| Processor SDK and optional Toolbox | Implemented contracts and optional tools | Uses extraction contracts; full Toolbox workflow parity is not implemented |
| Agent-maintained cited documentation wiki and MCP | Implemented | Filesystem MCP not exposed; hosted integration deferred |
| Topic map and frontend tool registry | Present in Local working-tree development | Not ported |
| Accounts, sessions, and roles | Not the hosted permission system | Present in Server working-tree development |
| PostgreSQL and OpenShift resources | Not Local's persistence/startup path | Present in Server working-tree development |
| Private uploads, private workspaces, retained private conversations, enterprise SSO | No claim of hosted isolation | Deferred |

Desktop installers, workstation image catalogs, Compose-based distribution,
multi-architecture publishing, and component-export workflows were previously
developed but are archived on `archive/workstation-deployment-2026-11-03`.
They are historical scope growth, not current supported entry points. Their
inclusion in any distribution must be identified separately from current Local
and Server source.

Other future concepts, including autonomous multi-step research, hosted
SharePoint/OneDrive ingestion, and isolated project workspaces, are not included
as implemented functionality by this specification.

## 7. Software, data, and external-resource boundaries

The expanded software scope consists of the application source, user interfaces,
API and SDK definitions, processing/orchestration logic, retrieval and
model-integration logic, database schemas and migrations, deployment templates,
tests, and accompanying technical documentation described above.

The following remain distinct from that software scope:

- Original documents, datasets, and user-provided expert guidance.
- Extracted corpus contents, generated summaries/wikis, embeddings, indexes,
  and operational databases produced when the software runs.
- User identities, passwords, sessions, API keys, certificates, internal URLs,
  and deployment-specific configuration.
- Third-party model weights, training data, inference services, and subscriptions.

Source text, images, prompts, or excerpts can leave the Core process when sent
to a selected extractor, enricher, or model service. The transmitted content
depends on the requested operation. “Local” describes the application and
persistence arrangement; it does not guarantee that every selected processor
or model runs on the same computer or that all operations are offline.

The source uses third-party libraries and programs for the web application,
document parsing, OCR, numerical operations, retrieval, database access, and
service transport. Examples include React/MUI, FastAPI/Pydantic, PyMuPDF and
pdfminer.six, Tesseract/OpenCV, NumPy/FAISS/BM25 libraries, and PostgreSQL-related
components. These are dependencies, not claims of OSII authorship. An exact
distribution requires its own versioned dependency and notice inventory;
software permission does not by itself determine permission to redistribute
input documents, model assets, or generated materials.

## 8. Source basis and release boundary

This specification was prepared from both development worktrees on the date
above:

| Worktree | Branch | Base commit inspected |
| --- | --- | --- |
| `osii` | `main` | `04d5c7e70d1bbf8abf692c7d0d3ec6cd41ffda41` |
| `osii-server` | `osii-server` | `66fdc915714352c188c3bfcbae9f0830416796f4` |

Both contained additional tracked and untracked development changes. The commit
IDs therefore identify the starting revisions, not complete immutable snapshots
of all functionality described here. A release scope should record the final
commit/tag for each included implementation and identify any archived components
included with it.

The principal Local references are the [architecture](../concepts/architecture.md),
[resource model](../reference/api/resource-model.md),
[extraction lifecycle](../reference/extraction-versions.md),
[transfer and deletion behavior](../operations/sensitive-data.md),
[Processor SDK](https://github.com/sandialabs/OSII/blob/main/osii-core/processor-sdk/README.md),
[MCP documentation workflow](https://github.com/sandialabs/OSII/blob/main/osii-mcp/README.md), and
[frontend/topic explorer specification](../extending/frontend-tools.md).

The Server evidence is in its separate worktree: `README.md`,
`docs/operations/runbook-server.md`, `osii-core/osii/server/`,
`osii-core/osii/persistence/`, `osii-core/osii/domain/library.py`,
`osii-core/osii/search/engine.py`, `osii-core/server-tests/`, and
`deploy/openshift/`. Older planning documents describe possible future designs;
they do not override the narrower implemented Server scope recorded here.
