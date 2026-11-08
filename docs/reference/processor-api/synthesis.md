# Synthesizer API: explain the evidence

A **synthesizer** produces readable Markdown from text OSII has already
extracted. Its job is to help a person understand an object, folder, collection
or whole-library scope while keeping the supporting evidence within reach.

**Python:** `Synthesizer.synthesize(request: SynthesisRequest) -> SynthesisResponse`

**HTTP:** `POST /v1/synthesize`

## When should I use it?

Use a synthesizer for a cited overview, a comparison of reports, or a concise
explanation. The method can select excerpts, use rules, or call a language
model. “Synthesizer” describes its responsibility, not a required technology.

Use an [extractor](extraction.md) to read source bytes. Use an
[enricher](enrichment.md) when the desired product is a structured table,
graph, entity list or reusable cited wiki artifact. Both can produce readable
text, but their output contracts serve different purposes.

Core supplies an explicit scope. A synthesizer does not secretly search for
more files or walk the library itself. That makes the result's evidence
boundary understandable to a researcher reviewing it later.

## Endpoint

`POST /v1/synthesize`

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
  "request_id": "explain-1",
  "scope": {
    "scope_type": "object",
    "scope_id": "file-1",
    "documents": [{
      "file_id": "file-1",
      "filename": "sensor.txt",
      "text": "The sensor passed."
    }]
  }
}
```

| Field | Type | Required / default | Meaning |
| --- | --- | --- | --- |
| `api_version` | string | No; `"v1"` | Only v1 is accepted |
| `request_id` | string | Yes | Caller-generated operation ID; echo unchanged |
| `scope` | ScopeInput | Yes | Explicit evidence boundary |
| `scope.scope_type` | string | Yes | `object`, `folder`, `collection`, or `root` |
| `scope.scope_id` | string | Yes | Caller-selected scope identity |
| `scope.documents` | DocumentInput[] | No; `[]` | Documents to analyze; no automatic discovery |
| `scope.metadata` | object | No; `{}` | Explicit scope/representation metadata |
| `scope.documents[].filename` | string | Yes per document | Source label |
| `scope.documents[].file_id` | string or null | No; `null` | Identity to cite |
| `scope.documents[].text` | string or null | No; `null` | Exact supplied text |
| `scope.documents[].segments` | TextSegment[] | No; `[]` | Identified evidence segments, when supplied |
| `scope.documents[].media_type` | string | No; `"application/octet-stream"` | MIME type |
| `scope.documents[].content_base64` | string or null | No; `null` | Shared model allows bytes; do not assume Core sends them |
| `scope.documents[].metadata` | object | No; `{}` | Explicit document metadata |
| `expert_context` | string or null | No; `null` | Human guidance, not citable evidence |
| `config` | object | No; `{}` | Non-secret settings validated by the method |
| `model_context` | ModelContext or null | No; `null` | Short-lived gateway access, normally supplied by Core |

The schema permits empty scopes and absent document text. Your method decides
whether to return an empty result with a warning or reject missing evidence.
The example reads only `document.text`; it never invents missing content.

## Response format

### Example response

This is the matching example result. Optional nulls and some default-valued
nested fields are omitted for readability; the SDK HTTP helper normally
serializes those defaults too. This is valid response JSON, not a schematic
with placeholders.

```json
{
  "api_version": "v1",
  "request_id": "explain-1",
  "processor": {
    "name": "demo.excerpts",
    "version": "1.0.0",
    "display_name": "Cited excerpt preview",
    "description": "Quotes supplied text; makes no new claims.",
    "kind": "synthesizer",
    "capabilities": {
      "scope_types": [
        "object",
        "folder",
        "collection",
        "root"
      ],
      "output_kinds": [
        "markdown"
      ]
    }
  },
  "markdown": "## sensor.txt\n\nThe sensor passed.",
  "citations": [
    {
      "file_id": "file-1",
      "char_start": 0,
      "char_end": 18
    }
  ],
  "metadata": {},
  "warnings": []
}
```

| Field | Type | Required / default | Meaning |
| --- | --- | --- | --- |
| `api_version` | string | No; `"v1"` | Protocol version |
| `request_id` | string | Yes | Unchanged request ID |
| `processor` | ProcessorDescriptor | Yes | Method identity and version |
| `markdown` | string | Yes; may be empty | Readable, derived explanation |
| `citations` | ProvenanceRef[] | No; `[]` | Supporting source locations |
| `metadata` | object | No; `{}` | Method/run details |
| `warnings` | string[] | No; `[]` | Missing evidence, truncation, or other limitations |

### ProvenanceRef

| Field | Type | Required / default | Meaning |
| --- | --- | --- | --- |
| `file_id` | string or null | No; `null` | Supplied source identity |
| `segment_id` | string or null | No; `null` | Supplied segment identity |
| `page` | integer or null | No; `null` | One-based page, minimum 1 |
| `char_start` | integer or null | No; `null` | Zero-based, inclusive start |
| `char_end` | integer or null | No; `null` | Zero-based, exclusive end |
| `source_origin` | object | No; `{}` | More precise source location |

Offsets refer to the exact supplied text, not PDF bytes, normalized whitespace,
or output Markdown. Use segment identity for a segment-relative span; document
identity for a span in the supplied document text. State that choice.

The schema allows an empty reference and checks only types/minimum values.
It does not enforce `char_end >= char_start`, bounds, source membership, or
claim support. v1 citations are a result-level list: there is no typed mapping
from a Markdown claim to its citation. Those are review/test responsibilities.

Empty Markdown and citations are schema-valid. Return an explanatory warning
when there is no evidence. Do not equate `200` with a grounded conclusion.

## Errors and operational behavior

These are synchronous JSON endpoints, not multipart uploads or background
job submissions. `200` returns the result, not a saved Core object.
The SDK helper returns `422` for malformed/invalid requests or a method's
`ValueError`; unhandled failures normally return `500`.
See [error examples and transport limits](index.md#errors-and-transport-limits)
for exact shapes, timeouts, authentication, and retry limits.

## Compliance checklist

- [ ] Consume only supplied scope evidence; handle absent text explicitly.
- [ ] Echo the request ID and identify the synthesizer/version.
- [ ] Return Markdown and defensible source references.
- [ ] Test offsets against exact input and verify every cited source exists.
- [ ] Distinguish generated interpretation from evidence and human guidance.
- [ ] Surface empty evidence, truncation, and contradictions.

These are implementation obligations, not a claim that every rule is
automatically enforced by the SDK. The
[backend review](index.md#backend-review-what-is-enforced-today) separates
schema checks from remaining hardening decisions.

## A small working example

This method quotes up to 160 characters per document and cites those exact
characters. It is a **deterministic excerpt preview**, not an AI summary.
Copy blocks 1–4 in order into `my_processor.py` or a Python session.

### 1. Import the contract

```python
from osii.processor_sdk import (
    Capability, DocumentInput, ScopeInput, Synthesizer,
    SynthesisRequest, SynthesisResponse, ProvenanceRef,
    ProcessorDescriptor, ProcessorKind, create_processor_app,
)
```

### 2. Describe and implement your method

```python
DESCRIPTOR = ProcessorDescriptor(
    name="demo.excerpts", version="1.0.0",
    display_name="Cited excerpt preview",
    description="Quotes supplied text; makes no new claims.",
    kind=ProcessorKind.SYNTHESIZER,
    capabilities=Capability(
        scope_types=["object", "folder", "collection", "root"],
        output_kinds=["markdown"],
    ),
)
```

```python
class ExcerptSynthesizer(Synthesizer):
    descriptor = DESCRIPTOR

    def synthesize(self, request: SynthesisRequest) -> SynthesisResponse:
        sections, citations = [], []
        for document in request.scope.documents:
            excerpt = (document.text or "")[:160]
            if not excerpt:
                continue
            sections.append(f"## {document.filename}\n\n{excerpt}")
            if document.file_id:
                citations.append(ProvenanceRef(
                    file_id=document.file_id,
                    char_start=0, char_end=len(excerpt),
                ))
        return SynthesisResponse(
            request_id=request.request_id, processor=self.descriptor,
            markdown="\n\n".join(sections), citations=citations,
            warnings=[] if sections else ["No supplied document text to quote."],
        )
```

We leave the excerpt's whitespace unchanged so citation offsets still refer
to the exact input. If your method reads `document.segments` instead, preserve
the segment identity and its own location information.

### 3. Call it directly

```python
request = SynthesisRequest(
    request_id="explain-1",
    scope=ScopeInput(
        scope_type="object", scope_id="file-1",
        documents=[DocumentInput(
            file_id="file-1", filename="sensor.txt",
            text="The sensor passed.",
        )],
    ),
)
processor = ExcerptSynthesizer()
result = processor.synthesize(request)
print(result.markdown)
print(result.citations[0].model_dump(exclude_none=True))
```

Markdown output:

```markdown
## sensor.txt

The sensor passed.
```

Its citation points to `file-1`, character range `[0, 18)` in the text sent
to the method. The end offset is exclusive.

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
remote_result = client.synthesize(request)
print(remote_result.markdown)
```

## Models, context and storage

A model-backed synthesizer declares `model_requirements={"chat": "required"}`.
Core can provide gateway access; the
[model-handler guide](../../extending/processor-development.md#use-a-language-model-without-learning-an-osii-client)
explains the adapter. Label model-generated interpretation clearly, preserve
citations, and surface missing or contradictory evidence.

Core can reuse saved [expert context](../osii-store.md#expert-context) for the
scope. The service receives that guidance; it is not additional source
evidence. A direct call saves nothing. When invoked through Core, the returned
synthesis is committed through Core's storage workflow.

## Troubleshooting

| What you see | What to check |
| --- | --- |
| Empty Markdown | Is `document.text` present, or does your method need to consume `segments`? |
| Citations highlight the wrong text | Calculate offsets before normalization, trimming or rewriting |
| A folder result omits documents | Inspect the explicit request scope; the processor does not discover files |
| Model requirement error | Select a chat connection in Setup, or supply valid gateway context through Core |
| Output reads like source truth | Label generated interpretation and cite its supporting evidence |

Next: [enrichment](enrichment.md) for structured knowledge, or
[embedding](embedding.md) for numerical text representations.


## Suggested titles and long inputs

The shared chat synthesizer requests a descriptive Markdown heading. Core stores
that heading as `metadata.document_title` with `title_method=model_generated`;
it is a derived suggestion, not a filename change. If no useful heading is
returned, the first short source line may supply a `source_first_line` heuristic.
Multi-document syntheses do not assign a title to any individual document.
Topic Explorer prefers these titles when their synthesis still matches the
primary extraction; filenames and paths remain visible.

The built-in chat synthesizer and model-provider bridge share
`osii.processors.synthesis.synthesize_bounded`. Source text is divided into
100,000-character windows by default, summarized, then reduced in groups of up
to four. All source windows are included. `window_chars` and
`max_input_windows` bound requests and cost; defaults allow 32 input windows.
Smaller-context models may require smaller windows. Intermediate summaries are
derived model output and can lose detail, so inspect the original evidence.
Hosted Intake estimates call counts from current extracted text, and saves
successful model calls privately in the run for retry. Estimates can change
when re-extraction changes the text. External processors retain their own
input limits; Core does not silently split arbitrary enrichment requests.
