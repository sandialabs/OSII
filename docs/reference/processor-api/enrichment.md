# Enricher API: add inspectable knowledge

An **enricher** turns existing evidence into a useful knowledge product:
a comparison table, a relationship graph, a list of entities or a cited wiki.
It adds derived knowledge alongside the source without redefining what the
source originally contained.

**Python:** `Enricher.enrich(request: EnrichmentRequest) -> EnrichmentResponse`

**HTTP:** `POST /v1/enrich`

## When should I use it?

This is usually the right extension point for your domain expertise.
You might compare laboratory measurements, identify equipment mentioned in
reports, or build a cited account of a research campaign.

An [extractor](extraction.md) reads what the source says.
A [synthesizer](synthesis.md) produces an explanation.
An enricher returns a standard knowledge artifact that people can browse
and agents can consume without custom dashboard code.

Core supplies the object, folder, collection or root scope. Your method works
on that explicit evidence, reports provenance, and returns its result. Core
owns saving it. A method can be deterministic or model-backed; label
heuristics and generated interpretations honestly.

## Endpoint

`POST /v1/enrich`

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
  "request_id": "knowledge-1",
  "scope": {
    "scope_type": "collection",
    "scope_id": "sensor-checks",
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
| `scope.metadata` | object | No; `{}` | Explicit scope metadata |
| `scope.documents[].filename` | string | Yes per document | Source label |
| `scope.documents[].file_id` | string or null | No; `null` | Identity for provenance |
| `scope.documents[].text` | string or null | No; `null` | Exact supplied text |
| `scope.documents[].segments` | TextSegment[] | No; `[]` | Identified evidence segments, when supplied |
| `scope.documents[].media_type` | string | No; `"application/octet-stream"` | MIME type |
| `scope.documents[].content_base64` | string or null | No; `null` | Shared model allows bytes; do not assume Core sends them |
| `scope.documents[].metadata` | object | No; `{}` | Explicit document metadata |
| `expert_context` | string or null | No; `null` | Human guidance on interpretation, not evidence |
| `config` | object | No; `{}` | Non-secret settings validated by the method |
| `model_context` | ModelContext or null | No; `null` | Short-lived gateway access, normally supplied by Core |

Core can reuse saved [expert context](../osii-store.md#expert-context).
Processors receive it explicitly; they do not traverse the library or sidecars.
An empty scope is schema-valid. The example returns an empty table for it;
a method that needs evidence should reject it or report the limitation.

## Response format

### Example response

This is the matching example result. Optional nulls and some default-valued
nested fields are omitted for readability; the SDK HTTP helper normally
serializes those defaults too. This is valid response JSON, not a schematic
with placeholders.

```json
{
  "api_version": "v1",
  "request_id": "knowledge-1",
  "processor": {
    "name": "demo.word-counts",
    "version": "1.0.0",
    "display_name": "Document word counts",
    "description": "Counts whitespace-separated words in supplied text.",
    "kind": "enricher",
    "capabilities": {
      "scope_types": [
        "object",
        "folder",
        "collection",
        "root"
      ],
      "output_kinds": [
        "table"
      ]
    }
  },
  "artifacts": [
    {
      "id": "word-counts",
      "kind": "word_counts",
      "media_type": "application/json",
      "standard_data": {
        "artifact_type": "table",
        "title": "Document word counts",
        "columns": [
          {
            "key": "document",
            "label": "Document",
            "data_type": "string"
          },
          {
            "key": "words",
            "label": "Words",
            "data_type": "integer"
          }
        ],
        "rows": [
          {
            "document": "sensor.txt",
            "words": 3
          }
        ],
        "row_provenance": [
          [
            {
              "file_id": "file-1",
              "char_start": 0,
              "char_end": 18
            }
          ]
        ]
      }
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
| `artifacts` | Artifact[] | Yes; at least one | Unique artifact IDs; every artifact requires `standard_data` |
| `metadata` | object | No; `{}` | Method/run details |
| `warnings` | string[] | No; `[]` | Missing evidence, partial results, or other limitations |

Each artifact requires `id`, `kind`, `media_type`, and `standard_data`.
`kind` is your method label; `standard_data.artifact_type` chooses the format.
Do not also supply `text`, `json_data`, or `data_base64`: exactly one payload
is allowed. Optional `source_origin` and `metadata` default to `{}`.
See the [complete artifact envelope](index.md#artifact-envelope).

| Product | SDK model | `artifact_type` |
| --- | --- | --- |
| Typed columns and rows | `TableArtifactData` | `table` |
| Nodes and relationships | `KnowledgeGraphArtifactData` | `knowledge_graph` |
| Named entities and mentions | `EntityListArtifactData` | `entity_list` |
| Markdown and citations | `WikiMarkdownArtifactData` | `wiki_markdown` |

[Standard artifacts](standard-artifacts.md) specifies every field, defaults,
validation rules, and a JSON example for each format.

**Empty result:** `artifacts: []` is invalid. A table with no rows, graph with
no nodes/edges, entity list with no entities, or wiki with empty Markdown is
schema-valid inside an artifact. Explain the absence in `warnings`.
The SDK requires standard formats; Core's remote enricher still accepts legacy
payloads and does not enforce the full typed response envelope. See the
[backend review](index.md#backend-review-what-is-enforced-today).

## Errors and operational behavior

These are synchronous JSON endpoints, not multipart uploads or background
job submissions. `200` returns the result, not a saved Core object.
The SDK helper returns `422` for malformed/invalid requests or a method's
`ValueError`; unhandled failures normally return `500`.
See [error examples and transport limits](index.md#errors-and-transport-limits)
for exact shapes, timeouts, authentication, and retry limits.

## Compliance checklist

- [ ] Consume only supplied evidence; handle missing/empty scopes.
- [ ] Echo the request ID and identify the enricher/version.
- [ ] Return at least one uniquely identified standard artifact.
- [ ] Use exactly one artifact payload and the correct discriminator.
- [ ] Validate table/graph/entity invariants and actual source grounding.
- [ ] Label derived/model-backed interpretation and surface limitations.

These are implementation obligations, not a claim that every rule is
automatically enforced by the SDK. The
[backend review](index.md#backend-review-what-is-enforced-today) separates
schema checks from remaining hardening decisions.

## A small working example

This example produces a word-count table, one row per supplied document.
“Word count” here means whitespace-separated tokens; it is not linguistic
analysis. The table is deliberately simple so you can replace the calculation
with your domain logic.

Copy blocks 1–4 in order into `my_processor.py` or a Python session.

### 1. Import the contract

```python
from osii.processor_sdk import (
    Artifact, Capability, DocumentInput, ScopeInput, Enricher,
    EnrichmentRequest, EnrichmentResponse, ProvenanceRef,
    ProcessorDescriptor, ProcessorKind,
    TableArtifactData, TableColumn, create_processor_app,
)
```

### 2. Describe and implement your method

```python
DESCRIPTOR = ProcessorDescriptor(
    name="demo.word-counts", version="1.0.0",
    display_name="Document word counts",
    description="Counts whitespace-separated words in supplied text.",
    kind=ProcessorKind.ENRICHER,
    capabilities=Capability(
        scope_types=["object", "folder", "collection", "root"],
        output_kinds=["table"],
    ),
)
```

Separate the calculation from the response envelope. This small function is
where you can start replacing the example with your own method:

```python
def count_documents(scope: ScopeInput) -> TableArtifactData:
    rows, provenance = [], []
    for document in scope.documents:
        text = document.text or ""
        rows.append({"document": document.filename, "words": len(text.split())})
        provenance.append(
            [ProvenanceRef(file_id=document.file_id, char_start=0, char_end=len(text))]
            if document.file_id else []
        )
    return TableArtifactData(
        title="Document word counts",
        columns=[
            TableColumn(key="document", label="Document"),
            TableColumn(key="words", label="Words", data_type="integer"),
        ],
        rows=rows, row_provenance=provenance,
    )
```

The class wraps that result in the standard API response:

```python
class WordCountEnricher(Enricher):
    descriptor = DESCRIPTOR

    def enrich(self, request: EnrichmentRequest) -> EnrichmentResponse:
        return EnrichmentResponse(
            request_id=request.request_id,
            processor=self.descriptor,
            artifacts=[Artifact(
                id="word-counts", kind="word_counts", media_type="application/json",
                standard_data=count_documents(request.scope),
            )],
        )
```

### 3. Call it directly

```python
request = EnrichmentRequest(
    request_id="knowledge-1",
    scope=ScopeInput(
        scope_type="collection", scope_id="sensor-checks",
        documents=[DocumentInput(
            file_id="file-1", filename="sensor.txt",
            text="The sensor passed.",
        )],
    ),
)
processor = WordCountEnricher()
result = processor.enrich(request)
print(result.artifacts[0].standard_data.rows)
```

Output:

```text
[{'document': 'sensor.txt', 'words': 3}]
```

The returned table includes row provenance pointing to the exact supplied
document text. Empty scopes produce an empty table in this example, not
invented observations. The example counts only `document.text`, so absent
text gives zero; a production method should warn or reject when needed.

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
remote_result = client.enrich(request)
print(remote_result.artifacts[0].standard_data.rows)
```

## From a demo to a domain method

Replace `count_documents` first. Keep its input explicit and return a standard
artifact. Then add non-secret settings, representative examples and provenance
checks. You can test that function without starting a web server.

For a model-backed method, declare the required capability in the descriptor
and use the [model-handler adapter](../../extending/processor-development.md#use-a-language-model-without-learning-an-osii-client).
A generated wiki is derived knowledge; provide citations and label uncertainty.
The model-backed wiki implementations live in
`osii-toolbox/llm-wiki-enrichers/`.

Finally register the running processor, run enrichment through Core, and
inspect the saved artifact in the dashboard. Direct Python/HTTP calls return
data but do not create a stored enrichment.

## Troubleshooting

| What you see | What to check |
| --- | --- |
| “Artifact must contain exactly one payload” | Supply `standard_data` without also supplying `text`, `json_data` or `data_base64` |
| Enrichment requires a standard format | Use one of the four models above, rather than an ad hoc result dictionary |
| Table provenance validation error | Match `row_provenance` length to the number of rows, or leave it empty |
| Result has no saved dashboard artifact | Register the service and invoke it through Core; direct calls do not persist |
| A broad analysis misses expected files | Inspect the requested scope and supplied documents; the service does not discover the corpus |

Next: [the four APIs](index.md) to compare boundaries, or
[processor development](../../extending/processor-development.md) for deployment.
