# CLI cheat sheet

## 1. Launch the FastAPI app / dashboard
From repo root:

```powershell
python -m uvicorn osii.main:app --reload --host 0.0.0.0 --port 8511
```

Open:

```text
http://localhost:8511/dashboard
```

---

## 2. Run one extractor on one file

### PDF extractor
```powershell
python -m osii.extraction.cli `
  ".\osii-data\source\reports\Q2_Status_Report.pdf" `
  --data-root ".\osii-data\source" `
  --osii-root ".\osii-data\.osii" `
  --extractor pdf_default
```

### Tika document extractor
```powershell
python -m osii.extraction.cli `
  ".\osii-data\source\reports\example.docx" `
  --data-root ".\osii-data\source" `
  --osii-root ".\osii-data\.osii" `
  --extractor tika
```

### Tika catchall
```powershell
python -m osii.extraction.cli `
  ".\osii-data\source\notes\experiment_log.txt" `
  --data-root ".\osii-data\source" `
  --osii-root ".\osii-data\.osii" `
  --extractor tika_catchall `
  --option chunk_chars=4000
```

---

## 3. Run one object-level synthesizer on one extracted object

### Describe
```powershell
python -m osii.synthesis.cli `
  --osii-root ".\osii-data\.osii" `
  --file-id "sha256-abc123..." `
  --synthesizer describe `
  --expert-context "These files are from a thermal calibration experiment."
```

### Recursive
```powershell
python -m osii.synthesis.cli `
  --osii-root ".\osii-data\.osii" `
  --file-id "sha256-abc123..." `
  --synthesizer recursive `
  --option chunk_char_target=8000 `
  --option combine_group_size=4
```

---

## 4. Run one folder-level synthesizer on one folder node

### Describe folder
```powershell
python -m osii.synthesis.folder_cli `
  --osii-root ".\osii-data\.osii" `
  --folder-id "00000000-0000-0000-0000-000000000101" `
  --synthesizer describe_folder `
  --expert-context "Interpret these files together as one experiment."
```

### Recursive folder
```powershell
python -m osii.synthesis.folder_cli `
  --osii-root ".\osii-data\.osii" `
  --folder-id "00000000-0000-0000-0000-000000000101" `
  --synthesizer recursive_folder
```

---

## 5. Build a full OSII collection

### Check available capabilities
```powershell
python -m osii.list_capabilities
```

### Extraction only
```powershell
python -m osii.build_collection `
  --data-root "./osii-data/source" `
  --osii-root "./osii-data/.osii"
```

### Extraction + object synthesis
```powershell
python -m osii.build_collection `
  --data-root "./osii-data/source" `
  --osii-root "./osii-data/.osii" `
  --synthesizer describe
```

### Extraction + object + folder synthesis
```powershell
python -m osii.build_collection `
  --data-root "./osii-data/source" `
  --osii-root "./osii-data/.osii" `
  --synthesizer recursive `
  --folder-synthesizer describe_folder
```

### Restrict to PDFs and DOCX
```powershell
python -m osii.build_collection `
  --data-root "./osii-data/source" `
  --osii-root "./osii-data/.osii" `
  --include-pattern "*.pdf" `
  --include-pattern "*.docx"
```

### Override extractor for everything
```powershell
python -m osii.build_collection `
  --data-root "./osii-data/source" `
  --osii-root "./osii-data/.osii" `
  --extractor tika
```

### Add context
```powershell
python -m osii.build_collection `
  --data-root "./osii-data/source" `
  --osii-root "./osii-data/.osii" `
  --synthesizer describe `
  --folder-synthesizer recursive_folder `
  --context "Focus on thermal calibration and grouped experiment interpretation."
```

---

## 6. Run hierarchy synthesis over an existing OSII store

### Object + folder + root synthesis
```powershell
python -m osii.build_synthesis `
  --osii-root "./osii-data/.osii" `
  --synthesizer describe `
  --folder-synthesizer recursive_folder
```

### Objects only
```powershell
python -m osii.build_synthesis `
  --osii-root "./osii-data/.osii" `
  --synthesizer describe `
  --objects-only
```

### Folders only
```powershell
python -m osii.build_synthesis `
  --osii-root "./osii-data/.osii" `
  --folder-synthesizer recursive_folder `
  --folders-only
```

### Root only
```powershell
python -m osii.build_synthesis `
  --osii-root "./osii-data/.osii" `
  --folder-synthesizer recursive_folder `
  --root-only
```

Note:
`--root-only` currently uses the selected folder synthesizer on the root folder scope. It should not silently reuse stale root-folder synthesis from a previous strategy.

---

## 7. Build embeddings / vector database over extracted text segments

### MiniLM build
```powershell
python -m osii.build_vector_index `
  --osii-root "./osii-data/.osii" `
  --embedding-model "osii-local-hashing-v1" `
  --batch-size 1 `
  --checkpoint-every 50
```
## Rescan source files against the OSII store

The rescan workflow compares the current source data root against the existing OSII store and reports:

- unchanged files
- changed files
- moved files
- missing source files
- new files

```powershell
python -m osii.rescan `
  --data-root ".\osii-data\source" `
  --osii-root ".\osii-data\.osii"
```

To print JSON output:

```powershell
python -m osii.rescan `
  --data-root ".\osii-data\source" `
  --osii-root ".\osii-data\.osii" `
  --json
```

Notes:
- embeddings are built **after** extraction/synthesis
- the embedding build uses resumable checkpointing under `.osii/embeddings/build/`
- checkpoint files are removed after successful completion
- overlong text segments are truncated before embedding; if a model returns a context-length error, the build retries with more aggressive truncation and skips only the problematic segment if needed

---
## 8. Query the vector database

### Query top 5 results
```powershell
python -m osii.query_vector_index `
  --osii-root "./osii-data/.osii" `
  --query "thermal calibration drift" `
  --top-k 5
```

### Query with explicit model override
```powershell
python -m osii.query_vector_index `
  --osii-root "./osii-data/.osii" `
  --query "power consumption over time" `
  --top-k 10 `
  --embedding-model "osii-local-hashing-v1"
```
## Run an enrichment on a scope

Object scope example:

```powershell
python -m osii.enrich_scope `
  --osii-root ".\osii-data\.osii" `
  --enricher stats_keywords `
  --scope-type object `
  --file-id "sha256-test123"
```

Collection scope example:

```powershell
python -m osii.enrich_scope `
  --osii-root ".\osii-data\.osii" `
  --enricher llm_wiki_stub `
  --scope-type collection `
  --collection-id "col-abc123"
```

## Apply a rescan

The rescan workflow may optionally apply safe reconciliation updates.

Apply mode may:

- update moved source paths in object metadata
- rebuild folder manifests and tree structure
- optionally re-extract changed and new files

```powershell
python -m osii.rescan `
  --data-root ".\osii-data\source" `
  --osii-root ".\osii-data\.osii" `
  --apply
```

To re-extract changed and new files during apply mode:

```powershell
python -m osii.rescan `
  --data-root ".\osii-data\source" `
  --osii-root ".\osii-data\.osii" `
  --apply `
  --extractor tika
```

## Rescan apply mode with automatic routing

```powershell
python -m osii.rescan `
  --data-root ".\osii-data\source" `
  --osii-root ".\osii-data\.osii" `
  --apply
```

This uses configured extractor routing to choose an extractor for changed and new files.


To force one extractor for all changed and new files:

```powershell
python -m osii.rescan `
  --data-root ".\osii-data\source" `
  --osii-root ".\osii-data\.osii" `
  --apply `
  --extractor tika
```

## Build lexical search index without embeddings

This command builds:

- the chunk manifest
- the BM25 lexical index

It does not call the embedding model server.

```powershell
python -m osii.build_lexical_index `
  --osii-root ".\osii-data\.osii"
```

Window chunking example:

```powershell
python -m osii.build_lexical_index `
  --osii-root ".\osii-data\.osii" `
  --chunking-method window `
  --chunk-size 1200 `
  --chunk-overlap 200
```

## Run the full backend pipeline

The backend provides a single CLI entry point for running the full pipeline:

- extraction
- file synthesis
- folder synthesis
- optional collection import
- optional collection synthesis
- optional enrichments
- embeddings and lexical index build

Default behavior uses:

- extractor: `tika`
- file synthesizer: `describe`
- folder synthesizer: `describe_folder`
- collection synthesizer: `collection_firstn`
- context: empty

Example:

```powershell
python -m osii.build_all `
  --data-root ".\osii-data\source" `
  --osii-root ".\osii-data\.osii" `
  --collection-file ".\config\my_collection.toml" `
  --enricher stats_keywords `
  --build-embeddings
```

This command:

- builds the OSII store
- runs file and folder synthesis
- imports the collection definition
- runs collection synthesis
- runs the requested enrichment
- builds embeddings and the lexical index
---
## 9. Useful dashboard URLs

### Home
```text
http://localhost:8511/dashboard
```

### Run workbench
```text
http://localhost:8511/dashboard/run
```

### Inspect object bundle
```text
http://localhost:8511/dashboard/inspect/<file_id>
```

### Inspect folder node
```text
http://localhost:8511/dashboard/folders/<folder_id>
```

---
## 10. Useful API endpoints

### Extractors
```text
GET /api/extractors
```

### Object synthesizers
```text
GET /api/synthesizers
```

### Folder synthesizers
```text
GET /api/folder-synthesizers
```

### Root descriptor
```text
GET /api/osii/root
```

### Root synthesis
```text
GET /api/osii/root/synth
```

### Dashboard root aggregate
```text
GET /api/dashboard/root
```

### Dashboard document aggregate
```text
GET /api/dashboard/docs/<file_id>
```

### Dashboard source file streaming
```text
GET /api/dashboard/docs/<file_id>/source
```

### Dashboard folder documents
```text
GET /api/dashboard/folders/<folder_id>/documents
```

### Dashboard search
```text
POST /api/dashboard/search
```

### Dashboard related docs
```text
GET /api/dashboard/docs/<file_id>/related
```

### Dashboard segment context
```text
GET /api/dashboard/docs/<file_id>/segments/<segment_id>/context
```

### Dashboard collections
```text
GET /api/dashboard/collections
POST /api/dashboard/collections
GET /api/dashboard/collections/<collection_id>
PATCH /api/dashboard/collections/<collection_id>
DELETE /api/dashboard/collections/<collection_id>
GET /api/dashboard/collections/<collection_id>/documents
POST /api/dashboard/collections/<collection_id>/documents
DELETE /api/dashboard/collections/<collection_id>/documents/<file_id>
```

### Search
```text
GET /api/search?q=thermal calibration drift&top_k=5
```
