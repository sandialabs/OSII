# OSII Local and OSII Server: Expanded Functional Scope

Date: 9 November 2026

Status: Technical scope specification for the expanded software

## 1. Purpose and baseline

OSII—the On-Store Intelligence Index—has expanded from a file-based information
architecture into a modular software system for inventorying, preparing,
exploring, searching, interpreting, and using documents and datasets. This
specification describes the additional application, processing, integration,
and hosted-service functionality in **OSII Local** and **OSII Server**.

For this specification, the original scope is assumed to encompass the OSII
file-based architecture: stable source identities; original-file references;
extracted text and location information; provenance; root, folder, document, and
collection representations; and inspectable `.osii` files that distinguish
source evidence from derived information. Existing concepts for summaries,
enrichments, embeddings, and rebuildable indexes are treated as architectural
foundations, rather than asserted to be new additions in themselves.

The expanded scope includes the executable functionality built around those
foundations, together with its interfaces, reusable components, supporting
tools, tests, and documentation. It encompasses interactive applications,
processing workflows, replaceable services, grounded question answering,
agent-assisted knowledge maintenance, and hosted database-backed applications.

The descriptions and examples are illustrative and non-exhaustive. The scope
includes combinations, adaptations, and extensions of these functional families
across Local and Server, including alternative user interfaces, storage backends,
processors, algorithms, model providers, and deployment arrangements. Named
technologies identify representative implementations rather than required
vendors or exclusive implementation methods. Current implementation details
describe availability; they do not define the outer boundary of the expanded
functional scope. Contemplated extensions are identified separately from
present capabilities.

## 2. Two application forms

| Aspect | OSII Local | OSII Server |
| --- | --- | --- |
| Intended use | A standalone library operated on a workstation or within a locally controlled environment. | One shared library accessed by authenticated users through a hosted service. |
| Authoritative persistence | Portable `.osii` records, with a separate local database for file metadata inventory and selected-processing records; derived catalogs and search indexes support access. | PostgreSQL records for extracted content, provenance, chunks, vectors, artifacts, collections, accounts, settings, and jobs. |
| Originals | References existing source files or accepts files through local intake workflows; extraction does not edit originals. | Reads a deployment-configured dataset from a read-only source volume. |
| Interface | Browser Workbench, Core APIs, Python interfaces, and a Model Context Protocol adapter. | Role-aware browser application and authenticated HTTP APIs. |
| Access model | Local operating-environment controls, without application user accounts or a login. | Reader, curator, and administrator accounts with server-enforced permissions and owned collections. |
| Delivery arrangements | Workstation processes, browser access, command-line and programmatic use. | Hosted application and worker processes, browser/API access, and containerized deployment including OpenShift. |

The two forms share information concepts and reusable functionality while
adapting persistence, identity, permissions, and operation to their environments.
Specific features may be available in one form before the other. Store migration
and interchange are explicit operations rather than assumed side effects of
switching application forms.

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
do not directly access the store or invoke model endpoints. The extension
mechanism supports additional analytical and task-oriented views without
requiring a separate application for each tool.

### 3.2 Controlled intake and processing

Local adds workflows for selecting existing files or folders, accepting uploads,
resolving a proposed processing scope, and previewing eligible, current, stale,
or blocked work before it is queued. Users can run extraction, summaries,
embeddings, or enrichments separately instead of repeating the entire pipeline.
Activity views expose processing progress and results.

File inventory provides an earlier, lighter-weight entry point. Users can scan
large directory trees or mounted shared drives for paths, sizes, formats,
timestamps, availability, and processing state before choosing which contents
to read. Metadata scanning operates without reading or hashing file contents
or invoking models. A persistent local inventory supports filtering, aggregate
summaries, paginated browsing, and export independently of extracted sidecars.

Users can capture filtered selections or reproducible samples, apply file/byte
budgets, and run selected extraction, OCR, synthesis, or enrichment stages.
Selected processing records content identities, responses, and provenance and
supports reuse of compatible results. Job controls include progress reporting,
pause/resume/cancel behavior, restart recovery, and bounded processing attempts.
This separates discovering a corpus from committing to the cost of processing it.

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

RAG strategy tooling also supports query decomposition, candidate retrieval,
optional reranking, context selection, and bounded iterative retrieval and
answering. Users and developers can compare strategy profiles and inspect the
selected evidence, ranking scores, retrieval steps, stopping conditions, elapsed
time, and available model-usage information. Strategies use explicit scopes and
call budgets; they can reuse local functions or remote services. These are
experimental orchestration capabilities in addition to ordinary library chat.

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
write, and revise. This supports workflows in which an assistant accumulates
source-cited software guidance, research findings, experimental lessons, and
other reusable knowledge while carrying out a task.

Saved pages remain derived and unreviewed. Citation validation checks locations
and scope membership, not whether the cited passage proves the written claim.
The current filesystem-oriented MCP adapter operates with Local; authenticated
hosted adapters are a related integration path.

### 3.6 Topic exploration

The Local topic explorer adds a visual map and related-document navigation over
an existing compatible embedding index. Core aggregates document vectors,
projects them into two dimensions using principal component analysis, and ranks
related documents using cosine similarity in the full vector space.

The view reports index identity, coverage, staleness, and projection limitations.
It does not generate embeddings during browsing, automatically assign topic
names, or treat graphical distance as a complete measure of relatedness.
Lexical hashing is distinguished from semantic embeddings. The topic-exploration
capability is available with both Local's vector indexes and Server's stored
vectors, through persistence-specific adapters. Scope selection, document
selection, map/list navigation, related-document discovery, and links back to
source views make the projection usable as part of a library workflow.

## 4. Processor and model integration

The expanded software includes a Processor SDK, service/client helpers, and a
versioned HTTP protocol for extraction, synthesis, embedding, and enrichment.
Descriptors advertise capabilities and configuration; typed requests carry one document or
a bounded scope snapshot; typed responses return segments, vectors, or artifacts.

Core controls dispatch, validation, provenance, and persistence. A conforming
processor receives explicit inputs rather than independent authority to browse
the corpus or change its authoritative records. The protocol permits new
implementations without changing the library's fundamental information model.

Included baseline services provide native document extraction, full-page OCR,
local extractive summaries, lexical-hashing embeddings, basic statistical
enrichment, and adapters to configured model services. Toolbox implementations
add region-based OpenCV/Tesseract OCR, tabular processing, and model-generated
narrative or concept/entity wikis. Model-backed document parsing includes
page-image preparation, extraction of text and layout elements, and page/region
provenance through integrations such as Banyan/Nemotron Parse. PDF, image,
office-document, and tabular formats are representative inputs; supported
formats depend on the selected implementation.

Service startup, selection for a processing route, and invocation are separate
operations. A running processor can advertise its capabilities before a user
chooses to send it documents or invoke its configured model. Processors may
operate in isolated local environments or as independently deployed services.

Model adapters connect to separately operated inference services, including
OpenAI-compatible endpoints and, in Local, local-model services such as Ollama.
An API-compatible service need not be operated by any particular vendor.
The application selects models and sends requests; model weights, training
systems, service subscriptions, and provider infrastructure are separate inputs.

Local exposes connection settings, model discovery, invocation tests, defaults,
and credential-source information in Setup. Server supports administrator-managed
connections and deployment defaults. Chat, embeddings, reranking, and specialized
parsing may use independent endpoints, credentials, and models; they can also
share a compatible service. A model catalog listing is distinct from successfully
invoking the selected capability.

A model gateway can give a processor controlled access to a selected model
connection without disclosing the underlying provider credential. Access can be
limited by tool, job, capability, connection, request size, expiry, and revocation.
Core retains responsibility for authorizing requests and attributing results.
Connection profiles and processing settings can be reused or transferred with
credential values kept separate from shareable configuration.

## 5. Additional OSII Server functionality

### 5.1 Database-backed shared library

Server provides authoritative database persistence, currently using PostgreSQL,
while retaining the separation of source evidence, provenance, and derived outputs.
The database holds extracted text, extraction records, source identifiers,
chunks, embeddings, artifacts, shared collections, configuration, and operational
state, including ownership and visibility for saved collections. Originals
remain on a separately managed source volume.

Only Core API and worker components access the database. Document processing
commits related records transactionally, and corpus revisions identify changes
used to rebuild retrieval caches. Server does not fall back to SQLite or an
empty `.osii` store if its database is unavailable. Schema migrations and first
administrator creation are explicit operations.

### 5.2 Accounts, sessions, and differentiated permissions

Server introduces application-managed password accounts and sessions:

- Readers browse documents, inspect evidence, search, ask questions, and manage
  their own private collections.
- Curators additionally process the configured dataset and publish or manage
  shared collections.
- Administrators additionally manage accounts and model selections.

The implementation includes password hashing, temporary-password changes,
session revocation following account/password/role changes, authenticated API
access, request-origin and cross-site request forgery checks, and recorded
administrative/access events. The browser reflects these permissions, while
the server checks permissions independently of which buttons are visible.

Collection ownership and visibility support personal organization alongside
shared curated groupings. Users can create, describe, rename, and delete their
collections and change their membership; authorized users can publish collections
for shared use. Concurrency checks protect edits that interact with visibility
changes. A private collection protects its saved membership and metadata while
the underlying corpus remains shared with the library audience.

The current service uses one shared document library. Private document workspaces,
user uploads, public registration, and enterprise single sign-on are contemplated
extensions, distinct from currently available collection privacy. Accounts,
session records, ownership, and audit events introduce operational user data
beyond the original document information architecture.

### 5.3 Hosted processing, retrieval, and model-use controls

A source browser exposes available folders and files before processing, and an
administrator can select an allowed subfolder of the mounted dataset. Processing
requests capture that selection so later setting changes do not redirect an
already queued job. Existing indexed documents remain available independently
of a subsequent source-folder selection.

A curator previews and queues processing of the selected source scope. A separate
worker claims jobs using database-backed leases and heartbeats, coordinates
corpus writes, extracts text, creates chunks, optionally obtains embeddings,
and commits results. Unchanged documents can be skipped; explicit reprocessing
repeats extraction and configured model calls.

The processing workflow also includes staged plans, extraction-version inspection,
selected downstream stages, registered processors, progress records, and job
controls. These provide repeatable operation and investigation of partial or
failed work while keeping canonical commits within Core.

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

Hosted delivery includes container definitions and deployment resources for
API, worker, extractor, dashboard, and database workloads. These specify storage,
configuration and secret references, service routing, health/readiness checks,
and network-policy boundaries. OpenShift is a current deployment target;
headless backend use and other compatible hosting arrangements are also within
the described functional scope. Deployment credentials and actual internal
endpoints remain environment-specific configuration.

Operating guidance covers dataset publication, explicit migrations, database
backup/restore with matching originals, and rollback compatibility. Core and
worker source mounts are read-only; processors have neither the source-volume
mount nor database credentials. Supporting functionality includes dependency
preparation, configuration validation, service supervision, logs, graceful
shutdown, diagnostics, release/build automation, and retrieval evaluation.
Availability, scale, and recovery characteristics depend on the deployed
configuration and its validation.

## 6. Implementation coverage and related extensions

The following summarizes present implementation coverage. It describes where
features can currently be used, rather than excluding combinations or related
implementations from the functional scope.

| Capability | OSII Local | OSII Server |
| --- | --- | --- |
| Browse, inspect sources, search, grounded answers | Implemented | Implemented for authenticated shared-library use |
| Metadata inventory and source selection | Persistent metadata-only inventory, selection, sampling, and export | Browsing and subfolder selection within the mounted source dataset |
| Intake and processing management | Local selection/upload, budgeted selections, and multi-step workflows | Curator-triggered planning, processing, job control, and reprocessing |
| Extraction lineage and version inspection | Version preservation, inspection, and primary-extraction selection | Database extraction records and version inspection |
| Editable text, package transfer, sensitivity annotations | Implemented Local workflows | Additional integration paths |
| Collections | Filesystem-backed organization and transfer | Owned private collections and published shared collections |
| Processor SDK, Toolbox, and model gateway | Implemented contracts, tools, and controlled model access | Registered processors and controlled model access; workflows vary by processor |
| Agent-maintained cited documentation wiki and MCP | Implemented | Authenticated hosted integration is an extension path |
| Topic exploration | Experimental interactive map and related-document navigation | Experimental map and related-document navigation over stored vectors |
| RAG strategy experiments | Bounded strategies, profile comparisons, reranking, and traces | Core retrieval and chat; additional strategy integrations can reuse the contracts |
| Independent model-capability connections | Configurable connections | Administrator-managed connections and deployment defaults |
| Accounts, sessions, and roles | Relies on the local operating environment | Implemented application accounts and permissions |
| Database and hosted deployment | Local inventory database plus portable sidecars | Shared relational persistence and hosted deployment resources |

Related extensions may include additional processors and document formats,
alternative retrieval/reranking strategies, richer visualizations, agent
workflows, new storage adapters, and integrations with external document or
knowledge services. Hosted private workspaces, private uploads, retained personal
conversations, and enterprise identity integration are contemplated extensions;
their inclusion here does not represent them as currently implemented.

Distribution-related functionality has also encompassed desktop installers,
workstation image catalogs, Compose deployments, multi-architecture image
publishing, and component-export workflows. These remain part of the description
of how the software's scope has grown, although they are not current supported
startup paths. Distribution and packaging may evolve independently of the
underlying information-processing functionality.

## 7. Software, data, and external-resource boundaries

The expanded software scope includes application and service implementations,
user interfaces, command-line and programmatic interfaces, API and SDK
definitions, processing/orchestration logic, storage and interoperability
adapters, retrieval and model-integration logic, database schemas and migrations,
deployment and packaging tools, configuration schemas and templates, tests,
examples, and accompanying technical documentation. It includes software for
creating, reading, validating, transforming, transferring, and managing the
information products described above.

The software's data formats and processing functions are distinguished from
particular content supplied to or produced by an installation. Relevant data
categories include:

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
components. Their identities, versions, and applicable terms remain separately
identifiable. The described scope includes OSII's integration, adaptation, and
interoperability functionality without attributing authorship of those external
components, input documents, or model assets to OSII.
