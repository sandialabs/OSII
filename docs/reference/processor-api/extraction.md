# Extractor API: read the source

An **extractor** turns one source document into text with enough location
information to trace it back to the original. PDF parsers, OCR services and
specialist instrument-file readers all fit here.

**Python:** `Extractor.extract(request: ExtractionRequest) -> ExtractionResponse`

**HTTP:** `POST /v1/extract`

## When should I use it?

Use an extractor when you are defining what the source contains: reading a
scan, recovering a table's original rows, or decoding a proprietary format.
Use a [synthesizer](synthesis.md) to explain existing text, or an
[enricher](enrichment.md) to add an interpretation alongside it.

This separation matters when you improve a method. Better OCR can produce a
new extraction version while the original remains unchanged. A generated
conclusion should not quietly become canonical source text.

## Endpoint

`POST /v1/extract`

Request and response `Content-Type: application/json`. Success: `200 OK`.
The Python method and the HTTP route use the same typed contract.
Unknown model fields are rejected; dictionaries such as `config` remain
method-specific. Omitted optional fields use the defaults below.

## Request format

### Example request

This is the exact request used by the Python example later on this page.

```json
{
  "api_version": "v1",
  "request_id": "read-1",
  "document": {
    "file_id": "file-1",
    "filename": "sensor.txt",
    "media_type": "text/plain",
    "content_base64": "VGhlIHNlbnNvciBwYXNzZWQu"
  }
}
```

| Field | Type | Required / default | Meaning |
| --- | --- | --- | --- |
| `api_version` | string | No; `"v1"` | Only v1 is accepted |
| `request_id` | string | Yes | Caller-generated operation ID; echo unchanged |
| `document` | DocumentInput | Yes | One source; never an implicit filesystem mount |
| `document.filename` | string | Yes | Source label, not a path to open |
| `document.content_base64` | string or null | No; `null` in schema | Inline bytes; this example and OCR require it |
| `document.media_type` | string | No; `"application/octet-stream"` | MIME type; supported formats are processor-specific |
| `document.file_id` | string or null | No; `null` | Core source identity, when known |
| `document.text` | string or null | No; `null` | Shared model allows text; raw extraction need not include it |
| `document.segments` | TextSegment[] | No; `[]` | Shared model allows existing segments; do not assume they are supplied |
| `document.metadata` | object | No; `{}` | Explicit source metadata |
| `expert_context` | string or null | No; `null` | Human guidance, not evidence |
| `config` | object | No; `{}` | Non-secret settings validated by the method |
| `model_context` | ModelContext or null | No; `null` | Short-lived gateway access, normally supplied by Core |

v1 sends source bytes inline. The schema does not validate base64, require a
payload, or impose a byte limit; the processor must validate what it can read.
An empty file and an absent payload are different cases.

## Response format

### Example response

This is the matching example result. Optional nulls and some default-valued
nested fields are omitted for readability; the SDK HTTP helper normally
serializes those defaults too. This is valid response JSON, not a schematic
with placeholders.

```json
{
  "api_version": "v1",
  "request_id": "read-1",
  "processor": {
    "name": "demo.utf8",
    "version": "1.0.0",
    "display_name": "UTF-8 text reader",
    "description": "Reads UTF-8 source bytes without modifying their text.",
    "kind": "extractor",
    "capabilities": {
      "media_types": [
        "text/plain"
      ],
      "file_extensions": [
        ".txt"
      ]
    }
  },
  "segments": [
    {
      "id": "document",
      "text": "The sensor passed.",
      "segment_type": "text",
      "source_origin": {
        "filename": "sensor.txt"
      }
    }
  ],
  "artifacts": [],
  "document_metadata": {},
  "warnings": []
}
```

| Field | Type | Required / default | Meaning |
| --- | --- | --- | --- |
| `api_version` | string | No; `"v1"` | Protocol version |
| `request_id` | string | Yes | Unchanged request ID |
| `processor` | ProcessorDescriptor | Yes | Method identity and version |
| `segments` | TextSegment[] | Yes; may be empty in schema | Ordered text; IDs unique within this response |
| `artifacts` | Artifact[] | No; `[]` | Source-derived images/tables/other payloads |
| `document_metadata` | object | No; `{}` | Document-level facts, such as page count |
| `warnings` | string[] | No; `[]` | Partial reading, blank pages, or other limitations |

### TextSegment

| Field | Type | Required / default | Meaning |
| --- | --- | --- | --- |
| `id` | string | Yes | Unique processor-local segment ID |
| `text` | string | Yes | Recovered text; empty string is schema-valid |
| `segment_type` | string | No; `"text"` | Descriptive, extensible label; not an enum |
| `source_origin` | object | No; `{}` | Defensible page/region/row location and method-specific details |
| `related_ids` | string[] | No; `[]` | Related segment identifiers; references are not schema-validated |

Return segments in your documented reading order. Core persists that order and
preserves `source_origin`, adding `processor_segment_id` to retain the local ID.
The SDK does not validate geometry, reading order, or confidence.

**Empty extraction:** HTTP 200 with `segments: []` is SDK-valid; explain why in
`warnings`. Core's current remote extractor treats it as a failed extraction,
even if artifacts are present. A partial result with segments and warnings can
be committed; callers must inspect warnings.

An extraction artifact carries exactly one payload (`data_base64`, `text`,
`json_data`, or `standard_data`). Its complete envelope is in the
[shared contract](index.md#artifact-envelope). Keep it source-derived.

## Errors and operational behavior

These are synchronous JSON endpoints, not multipart uploads or background
job submissions. `200` returns the result, not a saved Core object.
The SDK helper returns `422` for malformed/invalid requests or a method's
`ValueError`; unhandled failures normally return `500`.
See [error examples and transport limits](index.md#errors-and-transport-limits)
for exact shapes, timeouts, authentication, and retry limits.

## Compliance checklist

- [ ] Accept one explicit document; reject unsupported/missing source content.
- [ ] Echo the request ID and identify the extractor/version.
- [ ] Return unique segment IDs in documented reading order.
- [ ] Preserve source locations and distinguish coordinate units.
- [ ] Report unread pages, filtering, and empty/partial extraction.
- [ ] Return only source-derived artifacts; leave persistence to Core.

These are implementation obligations, not a claim that every rule is
automatically enforced by the SDK. The
[backend review](index.md#backend-review-what-is-enforced-today) separates
schema checks from remaining hardening decisions.

## A small working example

This example reads a UTF-8 text file from the bytes in the request. It needs
no model or running OSII stack. Copy blocks 1–4, in order, into
`my_processor.py` or a Python session.

### 1. Import the contract

```python
import base64

from osii.processor_sdk import (
    Capability, DocumentInput, Extractor,
    ExtractionRequest, ExtractionResponse,
    ProcessorDescriptor, ProcessorKind, TextSegment,
    create_processor_app,
)
```

### 2. Describe and implement your method

The descriptor tells people what this method can read. The method receives
the document itself; `filename` is a label, not permission to open a host path.

```python
DESCRIPTOR = ProcessorDescriptor(
    name="demo.utf8", version="1.0.0",
    display_name="UTF-8 text reader",
    description="Reads UTF-8 source bytes without modifying their text.",
    kind=ProcessorKind.EXTRACTOR,
    capabilities=Capability(media_types=["text/plain"], file_extensions=[".txt"]),
)
```

```python
class UTF8Extractor(Extractor):
    descriptor = DESCRIPTOR

    def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        encoded = request.document.content_base64
        if encoded is None:
            raise ValueError("Supply the source bytes in document.content_base64.")
        text = base64.b64decode(encoded, validate=True).decode("utf-8")
        return ExtractionResponse(
            request_id=request.request_id,
            processor=self.descriptor,
            segments=[TextSegment(
                id="document", text=text, segment_type="text",
                source_origin={"filename": request.document.filename},
            )],
        )
```

### 3. Call it directly

Use the SDK to construct the request. Base64 is only the transport encoding;
you still write ordinary Python around your parser.

```python
request = ExtractionRequest(
    request_id="read-1",
    document=DocumentInput(
        file_id="file-1", filename="sensor.txt", media_type="text/plain",
        content_base64=base64.b64encode(b"The sensor passed.").decode("ascii"),
    ),
)
processor = UTF8Extractor()
result = processor.extract(request)
print(result.segments[0].text)
```

Output:

```text
The sensor passed.
```

### 4. Expose the same implementation over HTTP

```python
app = create_processor_app(processor)
```

With blocks 1–4 saved as `my_processor.py`, install the package from the
OSII checkout root in your active Python environment, then start the service
from the folder containing that file (same commands on Mac, Windows, Linux):

```sh
python -m pip install ./osii-core
python -m uvicorn my_processor:app --host 127.0.0.1 --port 8091
```

If you have already installed `osii`, skip the install command.
Open `http://127.0.0.1:8091/docs`, choose the operation's **Try it out**,
and paste the request JSON above. Stop with Ctrl+C.
[Shared setup](index.md#run-your-processor) also covers `uv` and registration.

The same request can be sent through the typed HTTP client:

```python
from osii.processor_sdk import ProcessorClient

client = ProcessorClient("http://127.0.0.1:8091")
remote_result = client.extract(request)
print(remote_result.segments[0].text)
```

Neither direct call saves into a library. Core owns validation, extraction
versioning and persistence when you run extraction through its workflows.

## OCR confidence and geometry

**Do we support confidence? Yes, for the experimental
`toolbox.tesseract-opencv` extractor—not as a universal typed v1 field.**
It returns one segment per accepted region. Here is an illustrative segment,
not the output of the UTF-8 example above:

```json
{
  "id": "page-2-region-1",
  "text": "Grounded OCR text",
  "segment_type": "ocr_region",
  "source_origin": {
    "page": 2,
    "bbox": [0.1, 0.2, 0.7, 0.3],
    "polygon": [[0.1, 0.2], [0.7, 0.2], [0.7, 0.3], [0.1, 0.3]],
    "confidence": 0.96,
    "coordinate_space": "normalized-page",
    "page_width": 1000,
    "page_height": 1400
  }
}
```

| Existing Toolbox field / setting | Interpretation |
| --- | --- |
| `source_origin.page` | One-based document page |
| `source_origin.bbox` | `[left, top, right, bottom]`, normalized by rendered page width/height |
| `source_origin.polygon` | Normalized region corner points; may be null; pipeline orders TL, TR, BR, BL |
| Coordinate frame | Origin at page top-left; x rightward, y downward; not pixel coordinates |
| `page_width`, `page_height` | Rendered raster dimensions in pixels, not PDF points |
| `source_origin.confidence` | Region score in 0–1, computed from recognized word scores |
| `config.confidence_threshold` | Default `0.5`; allowed 0–1; rejects regions below it |
| Ordering | Pages in order; detected regions sorted top-to-bottom then left-to-right before filtering |

The score is an arithmetic mean of usable Tesseract word confidences divided
by 100, clamped to 0–1. It is not a calibrated probability that the text is
correct, nor a score comparable across all engines. No word-level scores are
returned by the Processor API adapter. Nonempty text with no usable word
scores currently falls back to **1.0**; that is an implementation limitation,
not evidence of certainty. Missing/unknown should be represented explicitly
in any future quality convention.

The threshold filters output; it does not report rejected-region counts or
scores. If no segment survives, the adapter returns a warning. A lower
threshold can retain more uncertain text, but cannot recover regions the
detector missed. Top/left sorting is a heuristic, not guaranteed reading order
for multi-column, rotated, or right-to-left layouts.

The baseline `local.tesseract-page-ocr` extractor returns page text and page
grounding, **without confidence, boxes, or polygons**. Generic `TextSegment`
has no typed `confidence`, `bbox`, or `polygon` property. Its free
`source_origin` accepts these keys but does not validate them. Other
extractors may omit them or use different coordinate conventions.

Core's remote extraction path preserves this metadata when storing segments.
That does not guarantee a confidence display: the dashboard PDF overlay
currently reads nested `regions` arrays, whereas this adapter returns a box
directly in each segment's `source_origin`. End-to-end UI alignment remains
a follow-up, not a capability promised by this spec.

The actual implementation and separate tool-native routes are documented in
`osii-toolbox/osii-tesseract/README.md`,
`docs/API.md`, and `docs/OSII_INTEGRATION.md` under that tool directory.
Those native routes are not the portable Processor API v1 contract.

## Guidance and limitations

`expert_context` can explain instrument names, units or an unusual document
layout. It is not citable source text. Core can save and reuse that guidance
with [expert context](../osii-store.md#expert-context); your processor receives
it explicitly. If a method requires it, reject missing guidance with an
actionable `ValueError`.

An extraction artifact must carry exactly one payload:
`data_base64`, `text`, `json_data` or `standard_data`. Keep its content
source-derived. Generated entity interpretations, summaries and wikis belong
to other kinds; see [canonical outputs](canonical-outputs.md).

## Troubleshooting

| What you see | What to check |
| --- | --- |
| HTTP 422 for source content | Confirm base64 bytes and the parser's expected encoding/file type |
| Duplicate segment-ID validation error | Assign IDs unique within one response, such as `page-2-region-3` |
| Correct text, weak grounding | Return the original page/region/row locations in `source_origin` |
| Direct result does not appear in OSII | Direct SDK calls do not commit it; register the service and run Core extraction |
| New parser quality needs testing | Compare a [new extraction version](../extraction-versions.md) against the original evidence |

The experimental Toolbox Tesseract service is a real implementation of this
contract: it returns `ocr_region` segments with page and region grounding.
It also has its own OCR endpoints and tuning UI, separate from
`/v1/extract`. Read its README at
`osii-toolbox/osii-tesseract/README.md` in your checkout.

Next: [synthesis](synthesis.md) for explaining the extracted text, or
[enrichment](enrichment.md) for adding a standard knowledge artifact.
