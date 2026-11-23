# Extractor routing

## Purpose

Extractor routing determines which extractor processes each source file during an ingest run.

The default route uses `local.native-text` for text-layer PDFs, Office files,
and supported text formats. Scanned PDFs and images need an OCR flow. Unsupported
formats produce an explicit error; choose a compatible processor in Setup.

Routing is configured externally so extractor selection is not hardcoded in the run pipeline.

---

## Named flows in Setup

For the beta UI, use **Setup → Processing flows**. Every flow has a name,
ordered file-type routes, primary reader and ordered fallbacks, synthesis and
enrichment methods, and embedding chunk sizes. **Save & test sample** saves it
under `[processing_flows.<id>]` in `processors.toml` and exercises bundled samples.
Select that name in **Intake & Queue**. All processing steps run by default.
A queued job holds a route snapshot; editing Setup cannot reorder its readers.
The first matching extension wins; fallback order runs left to right.

The top-level `[routes.extractor]` format below remains compatible for existing
API callers. If customized, it appears as **Saved extraction routing** among
named flows. It is not a second routing editor in the beta Setup interface.

## Config file

Location:

```text
<OSII application data>/profiles/<profile-id>/deployment/processors.toml
```

---

## Current schema

The file contains ordered routes:

Only custom overrides need to be saved. To send PDFs through the optional
OpenCV OCR processor, use:

```toml
[[routes.extractor]]
name = "pdf-ocr"
extractor = "toolbox.tesseract-opencv"
fallbacks = ["local.native-text"]
extensions = [".pdf"]

[[routes.extractor]]
name = "other-native"
extractor = "local.native-text"
fallbacks = []
extensions = ["*"]
```

---

## Rule semantics

Routing is evaluated in order from top to bottom.

For a given file:
1. inspect the file suffix in lowercase
2. test each route in order
3. the first matching route wins
4. OSII tries that route's `extractor`
5. if extraction fails, OSII tries each name in `fallbacks` from left to right
6. if no route matches, fallback behavior should be explicit in configuration

The dashboard editor lives under **Setup → Extractors → Extraction routing defaults**. Intake uses the saved policy by default; an explicit reader choice can override it for a selected batch.

In future grouped-input workflows, routing may evolve to select an extractor for a logical multi-file unit rather than an individual file.

---

## Matching rules

### Exact extension match
If a route contains:
```toml
extensions = [".pdf", ".docx"]
```
then files with those suffixes match.

### Catch-all match
If a route contains:
```toml
extensions = ["*"]
```
it matches all remaining files.

---

## Ordering guidance

Order matters.

Recommended pattern:
1. specific special-case extractors first
2. a single catch-all route last

Example:

```toml
[[routes.extractor]]
name = "dense-pdf"
extractor = "toolbox.tesseract-opencv"
fallbacks = ["local.native-text"]
extensions = [".pdf"]

[[routes.extractor]]
name = "other-native"
extractor = "local.native-text"
fallbacks = []
extensions = ["*"]
```

---

## Supported extractor names

Common extractor identifiers:
- `local.native-text`
- `local.tesseract-page-ocr`
- `toolbox.tesseract-opencv` when that optional service is registered

These names should match the dispatcher implementation in:

```text
osii-core/osii/extraction/dispatcher.py
```

---

## Current implementation behavior

### `native_text`
- runs inside the OSII Python process with no service or container
- extracts text-layer PDFs with PyMuPDF
- handles DOCX, PPTX, XLSX, and common text formats
- is the default route for `make dev`, but not for deployment containers
- does not provide OCR for scanned PDFs

### `pdf_default`
- intended for PDFs
- renders pages to images
- sends page images to Nemotron Parse
- writes one page segment per page
- writes `Picture` boxes to `artifacts/`

---

## Validation rules

The validator should check:
- `routes` is a list
- each route has `name`
- each route has `extractor`
- `fallbacks`, when present, is an ordered list without the primary extractor
  or duplicates
- each route has a non-empty `extensions` list
- only one catch-all route is allowed
- catch-all should be last
- extensions should begin with `.` or be `*`
- duplicate route names are not allowed
- routes after a catch-all are unreachable

---

## Design intent

Extractor routing is externalized because:
- extractor inventory will grow
- different deployments may want different defaults
- future UI editing of routes should not require code changes
- routing policy should remain independent from extractor implementation

---

## Setup controls and tool configuration

The routing section displays the active `processors.toml` path. **Load TOML** accepts
`[[routes.extractor]]` tables (or the older `[[routes]]` format), validates them,
and stages a draft. **Save routes** changes only routing, preserving other tool
settings. Invalid files leave saved configuration and the current draft intact.
Primary and fallback readers must accept every extension in a rule. A reader
with a limited extension list cannot be used for `*`. Processor API descriptors
supply `capabilities.file_extensions`; dispatch also checks this before sending
files. Unavailable services are gray but their saved routes remain inspectable.

The question-mark button explains rule order, fallbacks, TOML loading, and how
to add an extractor. Start with `osii-core/osii/extraction/` and `osii-processor-modules/`,
then read [the extraction API](processor-api/extraction.md) to build a service
that accepts bounded inputs and returns text with source locations.

Model-backed tools such as Wiki have their **Writing model endpoint** selector
in their own service row. Automatic uses the configured library default or an
enabled compatible connection; the resolved alias is displayed. Explicit choices
remain explicit. Endpoint health is shown by Model Connections; an automatic
choice cannot guarantee a remote service will remain reachable during a run.

## Archived Tika integration

The former Tika adapter, managed Java runtime, and their tests are preserved on
`archive/tika-2026-11-19`. They are absent from `main` discovery, startup, and
Setup. The archived runtime ran Java directly; it did not require Podman.

Previously saved `tika` / `tika_catchall` routes are adapted in memory to their
remaining fallback chain, or `local.native-text` when none remains. Named flows
use the same adaptation. The saved configuration and historical extraction
bundles are preserved; changed effective routes invalidate prior sample tests.
Retest the flow in Setup. Files outside native text support need a compatible
processor, and scans need an OCR flow.

Existing queued jobs retain their original route snapshots and run history.
A paused job requiring the archived reader must be cancelled and queued again
with an available flow; original results and completed work remain stored.
