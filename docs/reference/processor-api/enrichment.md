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

[Run the service](index.md#run-your-processor) and open
`http://127.0.0.1:8091/docs`. Send this to `POST /v1/enrich`:

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

From a Python caller:

```python
from osii.processor_sdk import ProcessorClient

client = ProcessorClient("http://127.0.0.1:8091")
remote_result = client.enrich(request)
print(remote_result.artifacts[0].standard_data.rows)
```

## Request reference

| Field | Required? | Meaning |
| --- | --- | --- |
| `request_id` | Yes | Caller-generated operation ID |
| `scope.scope_type` | Yes | `object`, `folder`, `collection` or `root` |
| `scope.scope_id` | Yes | Identity of the selected scope |
| `scope.documents` | No in the schema | Explicit input documents; defaults to an empty list |
| `documents[].filename` | Yes per document | Human-readable source name |
| `documents[].text`, `documents[].segments` | No | Evidence available to the method |
| `documents[].file_id` | No | Source identity for provenance |
| Scope/document `metadata` | No | Explicit contextual metadata |
| `expert_context` | No | Human guidance on interpretation; not evidence |
| `config` | No | Non-secret, method-validated settings |
| `api_version`, `model_context` | No in Python | See the [shared contract](index.md#the-shared-contract) |

Core can reuse saved [expert context](../osii-store.md#expert-context). Your
processor receives it in the request; it does not read sidecars or traverse
the library to discover more context.

## Response reference

| Field | Meaning |
| --- | --- |
| `request_id`, `processor`, `api_version` | Unchanged request ID, your descriptor, and `"v1"` |
| `artifacts` | Required nonempty list; artifact IDs must be unique within the response |
| `metadata` | Optional method/run information |
| `warnings` | Missing evidence, partial results or other limitations |

Each enrichment `Artifact` needs `id`, `kind`, `media_type` and
`standard_data`. `kind` is your descriptive method label; the nested
`standard_data.artifact_type` determines how the result is interpreted.

Choose one of these four formats:

| Knowledge product | SDK model | `artifact_type` |
| --- | --- | --- |
| Typed columns and rows | `TableArtifactData` | `table` |
| Nodes and relationships | `KnowledgeGraphArtifactData` | `knowledge_graph` |
| Named entities with mentions | `EntityListArtifactData` | `entity_list` |
| Readable Markdown with citations | `WikiMarkdownArtifactData` | `wiki_markdown` |

Full field references and examples are in [standard artifacts](standard-artifacts.md).
You can return several artifacts from one operation. v1 enrichment rejects
untyped arbitrary JSON/text payloads in place of `standard_data`; generic
legacy viewers are not the current extension contract.

For a table, column keys must be unique. `row_provenance` can be empty; when
populated, it must have one entry per row. Each entry is a list of
`ProvenanceRef` records. Returning an empty provenance entry is more honest
than inventing a source location.

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
