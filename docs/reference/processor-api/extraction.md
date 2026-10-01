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

Follow [Run your processor](index.md#run-your-processor), then open
`http://127.0.0.1:8091/docs`. Send this JSON to `POST /v1/extract`:

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

Or call the running service from Python with that same `request`:

```python
from osii.processor_sdk import ProcessorClient

client = ProcessorClient("http://127.0.0.1:8091")
remote_result = client.extract(request)
print(remote_result.segments[0].text)
```

Neither direct call saves into a library. Core owns validation, extraction
versioning and persistence when you run extraction through its workflows.

## Request reference

| Field | Required? | Meaning |
| --- | --- | --- |
| `request_id` | Yes | Caller-generated operation ID |
| `document` | Yes | One `DocumentInput` |
| `document.filename` | Yes | Source name, not a filesystem path to read |
| `document.content_base64` | Parser-dependent | Source bytes encoded as base64; required by this example |
| `document.media_type` | No | MIME type; defaults to `application/octet-stream` |
| `document.file_id` | No | Core's source identity, when already known |
| `document.metadata` | No | Explicit source metadata |
| `document.text`, `document.segments` | No | Available in the shared document model; do not assume raw-source requests contain them |
| `expert_context` | No | Human domain guidance; separate from evidence |
| `config` | No | Method settings; defaults to `{}` |
| `api_version`, `model_context` | No in Python | See the [shared contract](index.md#the-shared-contract) |

v1 sends source bytes inline, not through an implicit file mount. Bound document
size before accepting work. The SDK does not itself impose a byte limit.

## Response reference

| Field | Meaning |
| --- | --- |
| `request_id` | The unchanged request ID |
| `processor` | Your descriptor and method version |
| `segments` | Ordered `TextSegment` records; IDs must be unique in this response |
| `artifacts` | Optional source-derived artifacts such as page images or directly parsed tables |
| `document_metadata` | Optional document-level facts such as page count |
| `warnings` | Limitations or partial-reading notices |
| `api_version` | `"v1"` |

A `TextSegment` requires `id` and `text`; its `segment_type` defaults to
`"text"`. Add source locations in `source_origin`: a page, region, row or
another defensible location. `related_ids` can relate segments.

The example has one whole-file segment. For OCR, preserve each region's page
and coordinates and state whether those coordinates are pixels or normalized.
There is no fixed enum of segment types, and the SDK does not infer coordinate
conventions for you. Do not strip meaningful source text merely to simplify
a downstream summary.

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
