# Decision: a workbench of evidence, operations, and saved products

Status: accepted. Applies to OSII-local; server persistence and access control
remain separate concerns.

## Purpose

A better OCR engine, topic model, or recommendation method should fit into an
existing operation. It should not require a new sidebar page, private storage
layout, or processor-specific editor. A model endpoint is a resource used by a
method; it is not a tool, a document, or a job status.

## Resource model

| Resource | Meaning and current persistence |
| --- | --- |
| Source observation | A path, size, timestamps, mount identity, and access outcome observed by metadata discovery. The local volume SQLite inventory owns these records; discovery never opens document content. |
| Document | Content identity with source locations. Existing file IDs, manifests, and portable sidecars remain canonical. |
| Text representation | Extracted or corrected text, its extraction identity, and source spans. Changing preferred text does not silently validate dependent results. |
| Scope | A document, folder, collection, or library. A submitted scope tool freezes membership and bounded text excerpts in the durable job payload. |
| Operation | What the person wants to do: read text, summarize, suggest metadata, write a wiki, build embeddings, or analyze. This groups interchangeable methods. |
| Method | A reviewed native adapter or Processor SDK descriptor: identity, version, scope types, output kinds, model requirements, and configuration schema. |
| Model binding | An enabled compatible named connection, resolved before queuing. A run records the actual model name, connection alias, endpoint type, and configuration fingerprint; credentials remain outside products. |
| Run | Durable queued work, inputs, controls, errors, and a saved-result checkpoint. Intake and scope tools share the local processing worker and Activity. |
| Product | A derived typed artifact owned by Core. Wiki products have revisions, provenance, an active revision, and generated candidates. |
| Index or cache | Rebuildable data, such as embeddings or a topic projection. A picture in embedding space and a similarity ranking are distinct views over these data; neither assigns topic labels. |

Inferred metadata is a suggestion product. It does not become a filesystem fact
or a human correction. The independently runnable metadata method reuses the
same evidence-checking parser as synthesis's optional metadata step. That
bundled synthesis step remains compatible with existing Intake presets.

## Interfaces

Core's capability catalog adapts existing descriptors; it does not introduce
new Processor SDK kinds. A new OCR service belongs under **Read text** in
Intake; a new scope enricher appears under the existing action controls. Methods
returning an established format reuse the corresponding renderer. A genuinely
new visualization registers once in the frontend renderer registry. A whole
workspace, such as Topic Explorer, uses the route registry.

Core owns scope membership, canonical commits, model grants, and revision
history. External processors receive bounded SDK requests and return validated
standard artifacts. They do not browse the corpus or write sidecars. This is a
reviewed extension interface, not an untrusted browser-plugin sandbox.

## Runs and limits

Scope tools currently accept at most 1,000 scope members and 200,000 retained
text characters in total. Each member receives an equal excerpt allowance;
missing text is skipped, and oversized scopes are rejected before queuing.
Run provenance records membership, preferred representations, full-text hashes,
retained spans, and truncation. Processor-specific settings may impose smaller
limits. Intake's separate file-count, byte, and time budgets still apply.

Before queuing, Core validates scope, model compatibility, and supported simple
configuration types/ranges. A missing shipped `top` or `mid` wiki alias inherits
the library default; a real configured alias remains an explicit choice.
Unavailable custom choices produce an immediate actionable error. Run bindings
are pinned; a changed connection requires a new run rather than silently using
a different model. Gateway grants enforce the connection fingerprint as well.

Scope jobs recover through the existing worker queue. Retry reuses saved inputs;
a saved-result checkpoint prevents repeating completed work on resume. Model
requests are **at least once**: a worker lost after a provider response but
before result persistence can repeat that request. Pause/cancel is cooperative;
an in-flight request may finish and save a result before control takes effect.
Legacy standalone synthesis/full-index API jobs and model downloads have not
been migrated by this decision; the supported Intake and scope-tool paths use
the persistent worker. No cross-process or multi-machine collaboration is claimed.

## Wiki revisions

Every scope uses the same editor. Legacy standard Wiki Markdown imports as an
original revision on first edit. Saves require the expected current revision;
a stale save returns HTTP 409 and the browser keeps the draft. Drafts are keyed
by library, scope, and product. Generated candidates cannot replace a human
revision. Selecting an older or generated revision creates an explicit restore
revision. Human changes retain citations as provenance and flag grounding for
review.

The hidden `.history/` manifest contains complete immutable revision records
and the active pointer. Atomic replacement is the commit point; the familiar
artifact JSON remains a compatibility view. Core reads the manifest once one
exists. An unfamiliar valid payload written externally is retained as an
untracked human revision; a known older compatibility payload is treated as
a lagging view after interrupted publication. An OS lock serializes commits on the local store. Deletion tombstones
the active product while retaining history; it does not erase source evidence.
History is currently loaded as a whole, so it is intended for ordinary wiki
editing, not an unlimited high-volume revision stream.

## UI rules

Keep **Files** as home. Group Library, Tools, Add & process, and Configuration;
pin substantial workspaces and provide **All tools** for methods. Keep explanatory
copy in details, errors beside actions, and progress visible until a saved
result or explicit failure exists. Use icons with short labels and accessible
text; never make an emoji the only accessible name.

Discovery follows **Location → Discover → Select batch → Process** for small
folders and large shares. Traversal controls and metadata filters are progressive
disclosure, while batch count and byte budgets remain visible. Collection
statistics and supporting products collapse independently with remembered state.
