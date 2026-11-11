# Extractor routing

## Purpose

Extractor routing determines which extractor processes each source file during an ingest run.

The default route uses `local.native-text` for supported text-bearing formats
and tries `tika` if that fails. Other formats route to `tika`. An unavailable
Tika service is reported as such; scanned PDFs need OCR.

Routing is configured externally so extractor selection is not hardcoded in the run pipeline.

---

## Config file

Location:

```text
<OSII application data>/profiles/<profile-id>/deployment/tools.toml
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
extractor = "tika"
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
extractor = "tika"
fallbacks = []
extensions = ["*"]
```

---

## Supported extractor names

Common extractor identifiers:
- `local.native-text`
- `tika`
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

### `tika_catchall`
- intended as general fallback/default extractor
- uses Apache Tika over HTTP
- writes chunked text segments

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

## Likely future evolution

Possible extensions:
- route by MIME type
- route by glob pattern
- route by path prefix/folder
- route by file size threshold
- route by structured predicates
- route by grouped multi-file patterns

If that happens, preserve backward compatibility by:
- keeping extension-based routes valid
- adding optional fields instead of replacing the current schema

## Setup controls and tool configuration

The routing section displays the active `tools.toml` path. **Load TOML** accepts
`[[routes.extractor]]` tables (or the older `[[routes]]` format), validates them,
and stages a draft. **Save routes** changes only routing, preserving other tool
settings. Invalid files leave saved configuration and the current draft intact.
Primary and fallback readers must accept every extension in a rule. A reader
with a limited extension list cannot be used for `*`. Processor API descriptors
supply `capabilities.file_extensions`; dispatch also checks this before sending
files. Unavailable services are gray but their saved routes remain inspectable.

The question-mark button explains rule order, fallbacks, TOML loading, and how
to add an extractor. Start with `osii-core/osii/extraction/` and `osii-toolbox/`,
then read [the extraction API](processor-api/extraction.md) to build a service
that accepts bounded inputs and returns text with source locations.

Model-backed tools such as Wiki have their **Writing model endpoint** selector
in their own service row. Automatic uses the configured library default or an
enabled compatible connection; the resolved alias is displayed. Explicit choices
remain explicit. Endpoint health is shown by Model Connections; an automatic
choice cannot guarantee a remote service will remain reachable during a run.

## Apache Tika toolbox adapter

`osii-toolbox/tika-adapter` implements the HTTP integration. Existing `tika` and
`tika_catchall` routes remain valid; Core retains a delegating compatibility shim.
The upstream Apache Tika server must be installed and run separately by the user.
OSII neither bundles nor downloads Apache Tika, and never starts a JVM or container.

`make dev` (or the Windows dev command) starts only the small adapter on loopback
port 8102, in its independent toolbox environment. `OSII_START_TOOLBOX=false`
disables automatic wrapper startup. `OSII_TIKA_ADAPTER_PORT` changes its local
port. Existing routing and selection defaults are preserved.

In **Setup → Extractors → Apache Tika**, enter the separately managed Apache
Tika base URL in **Apache Tika endpoint** and click **Save endpoint**. The setting
persists in the active `tools.toml`:

```toml
[processor_settings.tika]
tika_endpoint = "http://127.0.0.1:9998"
chunk_chars = 4000
```

`TIKA_URL` and `OSII_TIKA_PORT` no longer configure Core. Transfer any prior
custom upstream address to the Setup field. The adapter defaults to loopback
9998 until changed. Readiness probes the saved upstream through the wrapper;
an unavailable upstream is gray while its endpoint remains editable.
The adapter receives only selected document bytes and returns plain text chunks
with extracted-text character offsets. It does not claim PDF page boxes or
original-file byte offsets. Canonical persistence remains in Core.
