# Extraction architecture

## Purpose

This document defines the extraction-layer architecture for `ai-ready-ingest`.

The extraction layer is responsible for:
- invoking backend extraction tools or model endpoints
- normalizing results into canonical OSII document bundles
- preserving provenance from every derived output back to the original source input
- writing outputs incrementally when possible

---

## Design goals

- one extractor abstraction for all backends
- one logical extraction unit processed at a time
- minimal coupling to UI, orchestration, or runs
- incremental writes for observability and partial success
- canonical outputs that are easy for both humans and readers to inspect

---

## Package layout

```text
ai-ready-ingest/osii/extraction/
  __init__.py
  base.py
  common.py
  dispatcher.py
  tika_service.py
  banyan_service.py
  cli.py
```

---

## Core abstraction

The architectural unit is the **extractor**, not the extractor backend.

An extractor:
- takes one logical extraction unit
- optionally uses expert context
- may call one or more backend tools internally
- emits canonical OSII files into the document bundle

Examples:
- `TikaCatchallExtractor`
- `PdfDefaultExtractor`

Backend tools are implementation details:
- Apache Tika
- Nemotron Parse
- future OCR/VLM services

A logical extraction unit is often one source file, but may also be a grouped multi-file unit such as an experiment input/output pair.

---

## Extraction contract

Extraction writes the following canonical per-document bundle:

```text
objects/<file_id>/
  meta.toml
  manifest.jsonl
  <!-- segments/ -->
  artifacts/
```

Run/process metadata should be recorded at run scope rather than duplicated inside every object bundle.

### `meta.toml`
What the source file or logical source unit is:
- source path or source identity
- filename or unit label
- mime when applicable
- size
- mtime
- hash

### `manifest.jsonl`
One record per derived output:
- text records
- artifact records
- source provenance for each

### `segments/`
Text-bearing extracted outputs such as:
- page text
- chunked text
- OCR text
- text generated from grouped file interpretation at the extraction stage when appropriate

### `artifacts/`
Non-text derived outputs such as:
- cropped images
- figure extracts
- future table crops or similar derivatives

---

## What extraction does not do

Extraction does **not** currently produce:
- synthesis outputs
- folder synthesis
- embeddings
- vector indexes
- keywords
- Q/A pairs

Those belong to downstream stages and should not be conflated with plain extraction.

---

## Incremental write model

For extractors that process multi-unit inputs such as PDFs:

1. initialize `meta.toml`
2. process one unit at a time, e.g. one page
3. write segment/artifact files as soon as they are produced
4. append corresponding records to `manifest.jsonl`
5. finalize extracted outputs for the logical unit

This supports:
- partial success
- crash observability
- large-document progress reporting
- simpler debugging

Run/process metadata should be tracked at run scope rather than object scope when possible.

---

## Current extractor implementations

### `tika_catchall`
- generic fallback extractor
- uses Apache Tika over HTTP
- chunks returned text into fixed-size text segments
- does not generate artifacts

### `pdf_default`
- PDF-specialized extractor
- renders each page to PNG
- sends each page image to Nemotron Parse
- reconstructs page text from returned boxes
- crops boxes labeled `Picture` into `artifacts/`
- writes one page segment per page

---

## Expert context

Extractors MAY accept optional free-text expert guidance.

When an extractor includes a prompt-driven step, this guidance SHOULD be incorporated into the prompt so that extraction is better informed by domain context.

Examples:
- "These images are electrical schematics."
- "These plots are calibration curves, not performance results."

Requirements:
- expert context is optional
- lack of expert context MUST NOT block extraction
- if expert context influences prompt-driven extraction, run metadata should record that it was used
