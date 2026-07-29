# OSII store structure

## Canonical on-disk layout

The OSII store is a file-based database organized around:

1. a clear root entry point
2. folder nodes
3. document object bundles
4. derived synthesis outputs layered onto those scopes
5. a post-build embeddings area for vector search

---

## Root layout

```text
.osii/
├── root.toml
├── root.synth.txt
├── folders/
│   ├── folder-<folder_id>.toml
│   ├── folder-<folder_id>.synth.txt
│   └── ...
├── objects/
│   └── <file_id>/
│       ├── meta.toml
│       ├── manifest.jsonl
│       ├── text.txt
│       ├── artifacts/
│       └── synth.txt
│       └── synth.toml
├── runs/
│   └── run-<timestamp>.toml
└── embeddings/
    ├── segments.faiss
    ├── segments.mapping.jsonl
    └── segments.meta.toml
```

There is intentionally **no extra `store/` layer**.

The root should be clear and composable. A top-level OSII store should behave like the topmost folder scope rather than as a semantically special collection.

---

## Root-level files

### `root.toml`
Provides a clear entry point into the OSII store.

Typical contents:
- root folder id
- created timestamp
- source root metadata
- build metadata

This is administrative and navigational, not the primary semantic interpretation of the store.

### `root.synth.txt`
The current/default derived synthesis output for the root scope.

This is the semantic interpretation a dashboard or MCP tool should consult before drilling down into folders and objects.

### Run metadata
Run/process metadata lives under:
```text
runs/
  run-<timestamp>.toml
```

This is where strategy/config/process metadata belongs, rather than duplicating it inside every object or synthesis output.

---

## Folder nodes

Each folder node has canonical artifacts:
- a manifest TOML file
- a structural summary text file

And may also have one current derived synthesis file:
- `folder-<folder_id>.synth.txt`

Example:
```text
folders/
  folder-<folder_id>.toml
  folder-<folder_id>.synth.txt
```

### Folder manifest
Contains:
- `folder_id`
- `path_hint`
- direct docs
- direct subfolders
- stats
- optional entrypoints


### Folder synthesis
`folder-<folder_id>.synth.txt`

This is the derived semantic interpretation of the folder:
- summary
- description
- guide
- domain-specific interpretation

Folder synthesis is especially important for grouped workflows such as experiment folders, simulation result sets, and other related collections of files.

---

ZZZ## Document object bundles
ZZZ
ZZZEach source file or logical extraction unit gets a stable object bundle keyed by `file_id`.
ZZZ
ZZZIn current implementations, this is usually one source file, but grouped multi-file units may also be represented as one logical object bundle if the extraction workflow requires it.
ZZZ
ZZZExample:
ZZZ```text
ZZZobjects/<file_id>/
ZZZ  meta.toml
ZZZ  manifest.jsonl
ZZZ  text.txt
ZZZ  artifacts/
ZZZ  synth.toml
ZZZ  synth.txt
ZZZ```
ZZZ
ZZZ### `text.txt`
ZZZThe canonical extracted text file for the object.
ZZZ
ZZZAll text-bearing segment records in `manifest.jsonl` point into this file using `span.char_start` / `span.char_end`.
ZZZ
ZZZThis keeps object bundles compact while preserving precise segment-level provenance.
ZZZ
ZZZ### `manifest.jsonl`
ZZZThe canonical inventory and provenance map for all derived outputs in the bundle.
ZZZ
ZZZOne line per derived item.
ZZZ
ZZZ#### Text example
ZZZ```json
ZZZ{
ZZZ  "kind": "text",
ZZZ  "id": "seg-000001",
ZZZ  "path": "text.txt",
ZZZ  "type": "page",
ZZZ  "span": {
ZZZ    "char_start": 0,
ZZZ    "char_end": 1842
ZZZ  },
ZZZ  "source_origin": {
ZZZ    "source_type": "pdf",
ZZZ    "unit_type": "page",
ZZZ    "page": 1
ZZZ  },
ZZZ  "related_ids": ["artifact-000001"]
ZZZ}
ZZZ```
ZZZ
ZZZ#### Image example
ZZZ```json
ZZZ{
ZZZ  "kind": "image",
ZZZ  "id": "artifact-000001",
ZZZ  "path": "artifacts/artifact-000001.png",
ZZZ  "type": "image",
ZZZ  "source_origin": {
ZZZ    "source_type": "pdf",
ZZZ    "unit_type": "region",
ZZZ    "page": 1,
ZZZ    "bbox": {
ZZZ      "xmin": 0.86,
ZZZ      "ymin": 0.00,
ZZZ      "xmax": 0.99,
ZZZ      "ymax": 0.017
ZZZ    },
ZZZ    "label": "Picture"
ZZZ  },
ZZZ  "related_ids": ["seg-000001"]
ZZZ}
ZZZ```
ZZZ
ZZZ### `artifacts/`
ZZZHolds non-text derived outputs such as:
ZZZ- cropped images
ZZZ- extracted figures
ZZZ
ZZZ### Object synthesis
ZZZ- `synth.toml`
ZZZ- `synth.txt`
ZZZ
ZZZThese are the current/default derived synthesis outputs for the object.

---

## Embeddings

The embeddings area is a post-build derived layer used for vector search over extracted text segments.

Example:
```text
embeddings/
  segments.faiss
  segments.mapping.jsonl
  segments.meta.toml
```

### `segments.faiss`
Stores vectors for text segments only.

### `segments.mapping.jsonl`
Maps FAISS row ids back to:
- `file_id`
- `segment_id`
- the relative text path
- source relpath
- source provenance (`source_origin`)
- whether the text was truncated before embedding

### `segments.meta.toml`
Records embedding metadata such as:
- model
- dimension
- normalization
- token/character limits
- truncation/skip statistics

This layer is derived and rebuildable and should not be treated as canonical extraction output.

---

## Hierarchical synthesis and navigation

The derived synthesis hierarchy is intended to support intelligent traversal:

- root entry point in `root.toml`
- folder structural summaries for cheap navigation
- folder synthesis for semantic narrowing
- object synthesis for understanding one extracted unit
- raw extracted segments/artifacts for detailed evidence

The embeddings layer provides an additional search mechanism over text segments once the hierarchy has been narrowed.

This is especially important for MCP tools, which should start broad and drill down only as needed.

---

## Stable identities

### `file_id`
- `sha256-<hex>`
- typically derived from raw file bytes
- path-independent

For grouped multi-file extraction units, a stable logical unit identifier may be needed even when no single file hash is sufficient.

### `folder_id`
- UUIDv4
- assigned by the ingest/orchestration pipeline

---

## Human interpretability

OSII is designed to remain understandable in a file explorer:
- a clear root entry point
- folder manifests and structural summaries for hierarchy navigation
- manifest records that tie every output back to the source
- plain text segments in `segments/`
- one current synthesis output per scope
- a clearly separate embeddings area for vector search

This allows:
- quick manual inspection
- exact machine traversal
- later agent or MCP-based navigation
