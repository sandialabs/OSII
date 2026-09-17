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
extractor = "local.native-text"
fallbacks = ["tika"]
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

The dashboard editor lives under **Setup → Extraction routing**. Intake uses
the saved policy automatically and does not maintain run-specific extractor
overrides.

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
fallbacks = ["tika"]
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
