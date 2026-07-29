# Single-file walkthrough

This walkthrough shows what happens when one extractor processes one logical extraction unit and how a synthesizer can then operate on that extracted bundle.

It is also a useful reference for contributors adding a new extractor or synthesizer.

---

## Source input

Example source:

```text
/data_root/reports/Q2_Status_Report.pdf
```

The extractor computes:
- `source_relpath`
- `file_id = sha256-...`
- basic metadata

In the simplest case, the logical extraction unit is one source file.
In more advanced cases, it may be a grouped unit such as an experiment input/output pair.

---

## Output bundle after extraction

The resulting OSII bundle is written to:

```text
/data_root/.osii/objects/<file_id>/
  meta.toml
  manifest.jsonl
  text.txt
  artifacts/
  synth.toml
  synth.txt
```

Run/process metadata is tracked at run scope rather than duplicated inside every object bundle.
---

## Step 1: `meta.toml`

The extractor writes source identity metadata first.

Example:

```toml
[file]
source_relpath = "reports/Q2_Status_Report.pdf"
filename = "Q2_Status_Report.pdf"
mime = "application/pdf"
size_bytes = 2483912
mtime_utc = "2026-04-28T18:22:11Z"

[hash]
sha256 = "abcd1234..."
```

This file answers:
- what is the source file or logical input unit?

---
## Step 2: write extracted text and artifacts

For a PDF extractor:
- each page contributes a text span within one shared `text.txt`
- any `Picture` boxes may produce image artifacts

Example outputs:

```text
text.txt
artifacts/
  artifact-000001.png
```

---
## Step 3: append manifest records

Each derived output gets a record in `manifest.jsonl`.

### Text page example
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

### Image artifact example
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

### Text chunk example
```json
{
  "kind": "text",
  "id": "seg-000010",
  "path": "text.txt",
  "type": "chunk",
  "span": {
    "char_start": 1843,
    "char_end": 3921
  },
  "source_origin": {
    "source_type": "generic_text",
    "unit_type": "chunk",
    "chunk_index": 10
  }
}
```

This file answers:
- what derived outputs exist?
- where are they stored?
- where did they come from in the original source input?

Text-bearing outputs now share one canonical `text.txt` file per object, with manifest spans identifying which portion belongs to which segment.

---
## Step 4: synthesis

Once extraction is complete, a synthesizer reads the extracted outputs and writes a derived synthesis artifact.

Example object-level output:

```text
synth.txt
```

This may be:
- a concise summary
- a recursive summary
- a qualitative description
- an artifact-oriented guide

For grouped extraction units or folders, synthesis may also occur at broader scopes such as folder or root level.

This stage is intentionally downstream of extraction so that multiple synthesis strategies can operate over the same canonical extracted bundle without changing it.

---
## Step 5: embeddings

After extraction and synthesis, a vector database may be built over extracted text segments.

Example outputs:

```text
/data_root/.osii/embeddings/
  segments.faiss
  segments.mapping.jsonl
  segments.meta.toml
```

This layer is derived and rebuildable.
It supports vector search over extracted text segments.

The mapping file preserves the association between each vector and:
- `file_id`
- `segment_id`
- the text file path
- original source path
- original `source_origin`

---
## How this helps someone adding a new extractor

If you add a new extractor, your main job is to produce the same bundle shape with good provenance:

- write source metadata
- write extraction outputs
- append one manifest record per output

The most important design question is:

> what should `source_origin` look like for this modality or grouped input unit?

That choice determines how future reader, UI, search, and RAG layers will interpret and trace the derived outputs back to source context.

---
## How this helps someone adding a new synthesizer

If you add a new synthesizer, your main job is to:
- read extracted outputs from the existing bundle or folder scope
- apply a strategy cleanly
- write a synthesis file

The most important design question is:

> what useful derived synthesis output should this strategy produce for later inspection or downstream use?

For example, some strategies may produce:
- a concise summary
- a qualitative description
- an artifact-oriented guide
- a structured report

---
## Why this matters

The extraction bundle is designed so that downstream systems can:
- inspect extracted outputs directly
- trace any output back to the source input
- reconstruct user-facing context in dashboards
- support grounded retrieval and evidence inspection later

The synthesis layer is designed so that multiple strategies can be tried without changing the canonical extraction bundle.

The embeddings layer provides efficient vector search over text segments once the hierarchy has been narrowed.

Together, these make the repo both operational and research-friendly.
