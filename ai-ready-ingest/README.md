# AI Ready Ingest

AI Ready Ingest is the OSII core backend for turning heterogeneous technical file collections into a structured, inspectable representation of extracted content and derived artifacts.

At a practical level, this repository helps technical teams process mixed collections such as reports, experiment folders, simulation outputs, and reference material; preserve extracted text, artifacts, and provenance in a consistent OSII store; build derived outputs over multiple scopes; and support retrieval workflows over extracted content.

This repository is responsible for:

- ingest and extraction
- canonical OSII storage
- scope-aware processing over objects, folders, collections, and the root
- derived synthesis and future enrichments
- embeddings and search support
- preferred-text-aware downstream behavior
- reconciliation and maintenance workflows
- backend capabilities consumed by downstream systems

This repository is not responsible for user-facing browsing or dashboard UX. User-facing data exploration lives in `osii-dashboard`, which consumes backend capabilities exposed by this repository.

---

## Human-readable overview

The core workflow is:

1. **Extract** useful content from source files  
   Parse one logical source unit at a time into canonical extracted text, metadata, provenance, and extracted artifacts.

2. **Organize** extracted content into OSII resources  
   Represent content as stable objects, processable scopes, attached artifacts, text representations, and processing metadata.

3. **Derive** higher-level outputs  
   Run synthesis and future enrichments over object, folder, collection, or root scopes, with multiple derived variants able to coexist.

4. **Index** extracted text for retrieval  
   Build embeddings and related index artifacts over derived chunks generated from preferred text representations.

5. **Maintain** the store over time  
   Reconcile the current source data root against the OSII store and classify content changes for rescan and maintenance workflows.

6. **Consume** backend capabilities downstream  
   Downstream systems can inspect, search, and chat over root, folder, collection, or object scopes without depending directly on file layout details.

This makes the repository useful both as a disciplined backend for technical content processing and as a foundation for downstream browsing, search, and agentic workflows.

---

## Core model

The backend is organized around three core concepts:

### Objects
Objects are stable content units, typically keyed by `file_id`.

### Scopes
A scope is any set of objects that can be processed together.

Supported scope types are:

- `root`
- `folder`
- `collection`
- `object`

Folders are structural scopes derived from the source hierarchy. Collections are logical scopes whose membership is independent of the source folder tree.

### Artifacts
Artifacts are outputs attached to an object or scope.

Artifact families include:

- canonical extraction artifacts
- text representations
- syntheses
- enrichments
- editorial or curated artifacts
- search and index artifacts

---

## Scope-aware operations

Search and chat operate over explicit scopes rather than assuming folder-only processing.

Supported scope types are:

- `root`
- `folder`
- `collection`
- `object`

Collections are logical scopes independent of the source folder hierarchy.
Folders are structural scopes derived from source organization.

The same backend operation may target either kind of scope.

## Scope-aware backend behavior

Search, chat, synthesis, and future enrichments should target explicit scopes.

Contributors should avoid implementing new behavior that assumes folder-only grouping when the same behavior is conceptually defined over a general scope.

---

## Storage model

The current storage implementation is file-based and rooted in `.osii/`.

The file layout is the current backend implementation. Public behavior is defined by backend resource semantics rather than by direct dependence on file paths.

This design supports a future migration from file-based storage to a database-backed implementation without changing the conceptual API.

---

## What this repository provides

### Canonical extraction
The extraction layer processes one logical source unit at a time and writes canonical OSII extraction artifacts.

### Scope-aware derived processing
Derived operations may target:

- one object
- one folder
- one collection
- the root

### Preferred-text-aware downstream behavior
Objects may expose more than one text representation, and downstream operations may resolve a preferred representation when that behavior is intended.

### Reconciliation and maintenance
The backend supports CLI-first maintenance workflows, including comparison of the current source data root against the OSII store.

### Backend capabilities for downstream consumers
User-facing consumers such as `osii-dashboard` interact with this backend through logical object, scope, search, and chat operations rather than through direct knowledge of the OSII file layout.

---

## Scope types

### Root
The root scope represents the entire OSII store.

### Folder
A folder scope represents a structural grouping derived from the source hierarchy.

### Collection
A collection scope represents a logical grouping of objects independent of the source hierarchy. Collections may be created manually, from file lists, from TOML definition files, from folder-derived membership, or from future workflow-specific operations.

### Object
An object scope represents one content unit.

---

## Artifact families

### Canonical extraction artifacts
These are baseline outputs derived directly from source input, such as:

- metadata
- provenance
- manifests
- canonical extracted text
- extracted artifacts

### Text representations
Objects may have multiple text representations.

The current backend supports:

- canonical extracted text
- editable text

Canonical extracted text remains preserved.
Editable text is represented separately and may be preferred for downstream operations when present.

Search, chat, and future enrichments should consume the preferred text representation when that behavior is intended.

### Syntheses
Objects and scopes may have multiple synthesis artifacts produced by different methods. One synthesis may be preferred for downstream use.

### Enrichments
Enrichments are rebuildable derived artifacts such as:

- keywords
- entities
- labels
- wiki generation
- future analytical outputs

### Editorial artifacts
Editorial artifacts are curated or user-supplied outputs such as corrected OCR text.

### Search and index artifacts
Embeddings, chunking outputs, and index artifacts support retrieval and search workflows.
They are derived artifacts and should follow preferred text resolution when that behavior is intended.

---

## Derived artifact families

Derived artifacts are stored separately from canonical extraction artifacts.

The backend supports dedicated locations for:

- syntheses
- enrichments

These artifact families may exist at:

- object scope
- folder scope
- collection scope
- root scope

Multiple variants may coexist for the same scope. Variants are distinguished by method and artifact kind.

This allows statistical, LLM-based, and future alternative methods to exist side by side without overwriting canonical extraction artifacts.

## Enrichment framework

The backend provides an enrichment framework for rebuildable derived artifacts that are not canonical extraction artifacts and are not limited to summary-style synthesis.

Examples include:

- keyword extraction
- entity extraction
- wiki generation
- future analytical outputs

Enrichments may target:

- object scope
- folder scope
- collection scope
- root scope

---

## Object processing metadata

Object resources expose processing metadata describing how the object was produced and what downstream capabilities apply.

Processing metadata includes:

- extractor identity
- synthesizer identity when available
- canonical text path
- editable text path when present
- capability flags for downstream consumers

Capability flags allow downstream consumers such as `osii-dashboard` to selectively enable UI features without inferring behavior directly from raw provenance files.

---

## Embedding chunks

Embedding and retrieval use derived chunks rather than canonical extraction segments.

Chunks are generated from the preferred text representation and stored under the embeddings area as index-preparation artifacts.

Canonical `manifest.jsonl` remains the source of truth for extraction provenance and document grounding.

This allows users to experiment with chunking strategies such as paragraph chunking or overlapping window chunking without rerunning extraction.

## Search grounding

Search results may be ranked using derived chunks, but grounding information returned to downstream consumers still refers to canonical object identity and text-span location.

This supports dashboard behaviors such as selecting text and jumping back to the document location without treating embedding chunks as canonical extraction units.

## Text span resolution

The backend exposes text-span resolution endpoints over canonical object text.

These endpoints support:

- retrieving text by character span
- retrieving surrounding text context by character span

Search results may be ranked using derived chunks, but downstream navigation and text interaction continue to use canonical object text spans for grounding.

---

## Main workflows

### Ingest a collection
Run extraction over a source data root and build canonical OSII object and scope artifacts.

### Process a scope
Run synthesis or future enrichments over an object, folder, collection, or root scope.

### Build embeddings
Generate derived chunks from preferred text representations and build a vector database over those chunks.

### Search and chat over scopes
Downstream consumers may search or chat over a root, folder, collection, or object scope.

### Maintain and reconcile the store
Compare the current source data root against the OSII store to support rescan, re-ingest, and maintenance workflows.

---

## Processing layers

### 1. Canonical extraction layer
Location:
- `ai-ready-ingest/osii/extraction/`
- canonical storage helpers in `app/domain/`

Responsibilities:
- process one logical source unit at a time
- write canonical extraction artifacts
- preserve provenance to source input

This layer owns baseline extracted content.

### 2. Derived processing layer
Location:
- `ai-ready-ingest/osii/synthesis/`
- future `app/enrichment/` or equivalent

Responsibilities:
- operate on existing objects or scopes
- produce syntheses and future enrichments
- support multiple methods and multiple variants
- consume preferred text representations when appropriate

This layer owns rebuildable derived outputs.

### 3. Scope and storage layer
Location:
- `app/domain/`

Responsibilities:
- represent objects and scopes
- manage collections
- resolve preferred text and artifact variants
- expose processing metadata and capability flags
- define backend semantics independently of storage implementation

### 4. Search and index layer
Location:
- `app/indexing/`
- `app/search/`

Responsibilities:
- build derived chunks for retrieval
- build embeddings
- manage index artifacts
- support scope-aware retrieval workflows
- consume preferred text representations when appropriate
- return grounding tied to canonical object identity and text spans

### 5. CLI maintenance layer
Location:
- CLI entry points under `app/`

Responsibilities:
- ingest
- synthesis and future enrichments
- embeddings
- rescan and reconciliation
- future merge workflows

---

## Current OSII store shape

The OSII store is the current file-based implementation of the backend.

```text
.osii/
├── root.toml
├── root.synth.txt
├── folders/
│   ├── folder-<folder_id>.toml
│   ├── folder-<folder_id>.overview.toml
│   ├── folder-<folder_id>.synth.toml
│   ├── folder-<folder_id>.synth.txt
│   └── ...
├── objects/
│   └── <file_id>/
│       ├── meta.toml
│       ├── provenance.toml
│       ├── manifest.jsonl
│       ├── text.txt
│       ├── editable_text.txt
│       ├── artifacts/
│       ├── synth.toml
│       └── synth.txt
├── runs/
│   └── *.toml
├── embeddings/
│   ├── segments.faiss
│   ├── segments.mapping.jsonl
│   └── segments.meta.toml
└── collections/
    └── ...
```

The exact collection storage implementation may evolve. Collections are backend scope resources and are not limited to folder hierarchy semantics.

The current backend stores canonical extracted text separately from editable text. Canonical extracted text remains preserved, and editable text may be selected as the preferred downstream representation when present.

Derived artifacts remain separate from canonical extraction artifacts and may exist as multiple method-specific variants across object, folder, collection, and root scopes.

Embedding chunks are derived index-preparation artifacts rather than canonical extraction units.

Object-facing resources may also expose processing metadata and capability flags for downstream consumers.

---

## Dependency direction

The intended dependency direction is:

```text
CLI / maintenance workflows
    ->
scope and storage layer
    ->
extraction / derived processing / indexing
```

Downstream consumers such as `osii-dashboard` consume backend capabilities exposed by this repository. They do not define storage semantics.

---

## Useful CLIs

### Build a full OSII collection
```powershell
python -m osii.build_collection `
  --data-root "./osii-data/source" `
  --osii-root "./osii-data/.osii" `
  --synthesizer describe `
  --folder-synthesizer recursive_folder
```

### Build synthesis over an existing OSII store
```powershell
python -m osii.build_synthesis `
  --osii-root "./osii-data/.osii" `
  --synthesizer describe `
  --folder-synthesizer recursive_folder
```

### Build embeddings
```powershell
python -m osii.build_vector_index `
  --osii-root "./osii-data/.osii" `
  --embedding-model "sentence-transformers/all-MiniLM-L6-v2" `
  --batch-size 1 `
  --checkpoint-every 50
```

### Create a collection from a file
Collections may be created from a TOML definition file.

```powershell
python -m osii.create_collection `
  --osii-root ".\osii-data\.osii" `
  --file ".\my_collection.toml"
```

Collections are logical scopes independent of source folder structure.

### Query the vector database
```powershell
python -m osii.query_vector_index `
  --osii-root "./osii-data/.osii" `
  --query "thermal calibration drift" `
  --top-k 5
```

For a larger command reference, see `docs/CLI_CHEATSHEET.md`.

---

## Reconciliation and maintenance

The backend provides a rescan workflow that compares the current source data root against the OSII store.

This workflow classifies files as:

- unchanged
- changed
- moved
- missing source
- new

Reconciliation is a core maintenance behavior of the OSII backend.

---

## Launch the server

From the repository root, run:

```powershell
python -m uvicorn osii.main:app --reload --host 0.0.0.0 --port 8511
```

If you see:

```text
ModuleNotFoundError: No module named 'app'
```

make sure you launched the command from the repository root, not its parent directory.

---

## Useful APIs

API surface may evolve, but commonly used routes include the following.

### OSII inspection
- `GET /api/osii/root`
- `GET /api/osii/root/synth`
- `GET /api/osii/folders`
- `GET /api/osii/docs/{file_id}`

### Search and embeddings
- `GET /api/search`
- `POST /api/embeddings/build`
- `GET /api/embeddings/meta`

### Capability discovery
- `GET /api/extractors`
- `GET /api/synthesizers`
- `GET /api/folder-synthesizers`

If this repository currently exposes additional dashboard-oriented routes, they should be understood as backend support endpoints rather than as ownership of dashboard UX.

---

## Design principles

- canonical extraction remains disciplined
- collections are first-class backend scopes
- derived artifacts are separate from canonical extraction artifacts
- canonical extracted text remains preserved
- editable text is stored separately and may be preferred for downstream use
- file-based storage is the current implementation, not the public contract
- downstream systems consume logical backend capabilities rather than file layout assumptions
- search, chat, synthesis, and future enrichments are scope-aware operations
- preferred text resolution should be explicit in downstream behavior
- downstream capability enablement should be driven by exposed processing metadata rather than raw storage inference
- reconciliation is a core backend maintenance behavior
- multiple derived variants may coexist without overwriting canonical extraction artifacts
- embedding chunks are derived retrieval artifacts, not canonical extraction units
- search grounding remains anchored to canonical object identity and text spans

---

## Run the tests

From the repository root:

```powershell
pytest
```

To run a specific test file:

```powershell
pytest tests/test_collections.py
```

To run one specific test:

```powershell
pytest tests/test_dashboard_api.py -k dashboard_doc_endpoint
```

For more verbose output:

```powershell
pytest -v
```

---

## Where to look next

- [Documentation index](../docs/index.md)
- [Architecture](../docs/concepts/architecture.md)
- [OSII store structure](../docs/reference/osii-store.md)
- [Contributor guide](../docs/contributing/developer-guide.md)
- [Extraction architecture](../docs/concepts/extraction.md)
- [Synthesis architecture](../docs/concepts/synthesis.md)
- [API overview](../docs/reference/api/index.md)
- [CLI cheat sheet](../docs/reference/cli.md)
