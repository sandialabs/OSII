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

[Run the service](index.md#run-your-processor) and open
`http://127.0.0.1:8091/docs`. Send this to `POST /v1/synthesize`:

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

The Python HTTP call uses the same request:

```python
from osii.processor_sdk import ProcessorClient

client = ProcessorClient("http://127.0.0.1:8091")
remote_result = client.synthesize(request)
print(remote_result.markdown)
```

## Request reference

| Field | Required? | Meaning |
| --- | --- | --- |
| `request_id` | Yes | Caller-generated operation ID |
| `scope.scope_type` | Yes | `object`, `folder`, `collection` or `root` |
| `scope.scope_id` | Yes | Identity of the selected scope |
| `scope.documents` | No in the schema | Explicit documents to analyze; defaults to an empty list |
| `documents[].filename` | Yes per document | Human-readable document name |
| `documents[].text` | No | Supplied text representation; may be absent |
| `documents[].segments` | No | Supplied identified segments; available when the caller includes them |
| `documents[].file_id` | No | Source identity to use in citations |
| `scope.metadata`, document `metadata` | No | Explicit scope/representation metadata |
| `expert_context` | No | Human guidance, such as “compare calibration changes” |
| `config` | No | Validated method settings; defaults to `{}` |
| `api_version`, `model_context` | No in Python | See the [shared contract](index.md#the-shared-contract) |

The shape permits empty scopes. Your method decides whether to return an empty
result with a warning or reject missing evidence. Do not invent content to fill
the gap. The example consumes only `document.text`.

## Response reference

| Field | Meaning |
| --- | --- |
| `request_id`, `processor`, `api_version` | Unchanged request ID, your descriptor, and `"v1"` |
| `markdown` | Required readable output |
| `citations` | Optional list of `ProvenanceRef`; supply defensible evidence for claims |
| `metadata` | Optional method details, such as document count |
| `warnings` | Missing evidence, truncation or other limitations |

A `ProvenanceRef` can carry `file_id`, `segment_id`, one-based `page`,
zero-based `char_start`/`char_end`, and `source_origin`.
Use the narrowest location you can defend. Character offsets refer to the
**exact supplied text**, not the original PDF bytes, cleaned whitespace or
your output Markdown. A file-level citation alone can be useful, but is less
precise than a supported segment or character span.

The SDK validates field types and nonnegative offsets; it does not prove a
claim is supported or that a span is in range. Test grounding explicitly.

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
