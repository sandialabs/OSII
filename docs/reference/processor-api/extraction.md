# Extraction API

`POST /v1/extract` converts one source document into canonical text segments
and source-derived artifacts.

An extractor is the right extension point when specialist logic defines what
the document fundamentally says—for example, reconstructing text from a known
PDF table layout.

## Request

```json
{
  "api_version": "v1",
  "request_id": "run-42:file-7",
  "document": {
    "file_id": "sha256-optional",
    "filename": "experiment-007.pdf",
    "media_type": "application/pdf",
    "content_base64": "JVBERi0x...",
    "metadata": {"source_relpath": "batch-4/experiment-007.pdf"}
  },
  "expert_context": "These reports use the 2025 instrument layout.",
  "config": {"header_y": 72}
}
```

Source bytes use base64 in v1. The core should enforce configured byte limits
before calling the service. `file_id` can be absent during intake.

## Response

```json
{
  "api_version": "v1",
  "request_id": "run-42:file-7",
  "processor": {"...descriptor": "..."},
  "segments": [{
    "id": "page-1-table-1",
    "text": "Temperature | Pressure\n21.4 | 100.2",
    "segment_type": "table",
    "source_origin": {"page": 1, "bbox": [90, 120, 510, 430]}
  }],
  "artifacts": [],
  "document_metadata": {"page_count": 12},
  "warnings": []
}
```

Segment IDs must be unique within the response. `source_origin` should contain
enough page/region information for the core to preserve grounding. Extraction
artifacts are source-derived images or structured data, not summaries.

See `examples/extractor.py`.
