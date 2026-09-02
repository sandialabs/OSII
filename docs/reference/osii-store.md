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
├── expert-context.md             # optional root guidance
├── folders/
│   ├── folder-<folder_id>.toml
│   ├── folder-<folder_id>.synth.txt
│   └── ...
├── objects/
│   └── <file_id>/
│       ├── meta.toml
│       ├── manifest.jsonl
│       ├── text.txt
│       ├── expert-context.md     # optional document guidance
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

## Expert context

Expert context is **human-supplied guidance, not extracted evidence**. In Intake,
enter domain facts such as “These are SEM images; scale bars are in microns;
describe cracks separately from preparation artifacts.” OSII saves the text
atomically for each matched document, including when extraction is skipped or
the selected processor fails. New nonblank context replaces the current text;
leaving the field blank preserves and reuses it on later runs.

| Scope | Canonical context file, relative to `.osii/` |
| --- | --- |
| Document | `objects/<file_id>/expert-context.md` |
| Collection | `collections/<collection_id>/expert-context.md` |
| Folder | `folders/folder-<folder_id>.expert-context.md` |
| Root | `expert-context.md` |

An Intake folder selection applies its guidance to each matched document, not
to unrelated documents in the library. Intake also saves collection context
when the run targets a logical collection. Other scope context can be saved
through the Python functions below. There is no implicit root/folder/collection
inheritance or merging: each method uses guidance for its **exact scope**.

Tesseract OCR, Apache Tika, and native text extraction need no expert context
and do not use it to alter recognized text. Saving it during OCR is still useful
for later image description, synthesis, or enrichment. Core sends resolved
guidance explicitly in the Processor API `expert_context` field; the processor
decides how to use it. A custom VLM that requires domain guidance should reject
missing context with an actionable validation message. The legacy Nemotron
layout parser remains image-only; it is not a context-aware image-description
processor merely because it uses a vision model.

Remote synthesis/enrichment adapters, the LLM Wiki enricher, and context-aware
in-process synthesizers reuse saved guidance. A processor receiving context is
not proof it used it: extraction provenance distinguishes supplied guidance from
the `expert_context_used = false` of context-free built-in parsers. Extraction
versions keep their own `expert-context.md` snapshot; promoting an older
extraction does not overwrite the current guidance. Editing guidance does not
automatically regenerate existing outputs—queue the affected steps again.

```python
from pathlib import Path
from osii.expert_context import load_expert_context, save_expert_context

store = Path("demo-workspace/.osii")
scope = {"scope_type": "object", "file_id": file_id}  # ID returned by extraction
save_expert_context(store, scope, "SEM images; scale bars are in microns.")
print(load_expert_context(store, scope))
# Later extraction/synthesis can omit expert_context to reuse this text.
# Explicitly clear current guidance when needed:
# save_expert_context(store, scope, "")
```

Context is portable library data, not a secret store: it may contain sensitive
domain information and is sent to the selected processor. Do not put credentials
in it. Clearing the current sidecar does not redact historical extraction
snapshots, intake manifests, or already generated outputs. For sensitive-data
removal, follow the [deletion workflow](../operations/sensitive-data.md).
Older intakes retain context in `manifests/intake-manifest-*.json`; they are not
silently promoted to document guidance. Re-enter the desired context once in
Intake (or use `save_expert_context`) to enable later reuse for those documents.

## Document object bundles

Each source file or logical extraction unit gets a stable object bundle keyed by `file_id`.

In current implementations, this is usually one source file, but grouped multi-file units may also be represented as one logical object bundle if the extraction workflow requires it.

Example:
```text
objects/<file_id>/
  meta.toml
  manifest.jsonl
  text.txt
  artifacts/
  synth.toml
  synth.txt
```

### `text.txt`
The canonical extracted text file for the object.

All text-bearing segment records in `manifest.jsonl` point into this file using `span.char_start` / `span.char_end`.

This keeps object bundles compact while preserving precise segment-level provenance.

### `manifest.jsonl`
The canonical inventory and provenance map for all derived outputs in the bundle.

One line per derived item.

#### Text example
```json
{
  "kind": "text",
  "id": "seg-000001",
  "path": "text.txt",
  "type": "page",
  "span": {
    "char_start": 0,
    "char_end": 1842
  },
  "source_origin": {
    "source_type": "pdf",
    "unit_type": "page",
    "page": 1
  },
  "related_ids": ["artifact-000001"]
}
```

#### Image example
```json
{
  "kind": "image",
  "id": "artifact-000001",
  "path": "artifacts/artifact-000001.png",
  "type": "image",
  "source_origin": {
    "source_type": "pdf",
    "unit_type": "region",
    "page": 1,
    "bbox": {
      "xmin": 0.86,
      "ymin": 0.00,
      "xmax": 0.99,
      "ymax": 0.017
    },
    "label": "Picture"
  },
  "related_ids": ["seg-000001"]
}
```

### `artifacts/`
Holds non-text derived outputs such as:
- cropped images
- extracted figures

### Object synthesis
- `synth.toml`
- `synth.txt`

These are the current/default derived synthesis outputs for the object.

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
