# Embedder API: represent text as vectors

An **embedder** maps identified text inputs to numerical vectors. It is a
replaceable calculation: Core owns text/chunk identity and index persistence;
the embedder owns the representation.

**Python:** `Embedder.embed(request: EmbeddingRequest) -> EmbeddingResponse`

**HTTP:** `POST /v1/embed`

## When should I use it?

Use an embedder when your retrieval or analysis method needs vectors.
Embedding is optional: OSII's model-free search can use lexical/BM25 retrieval.
You do not need a downloaded embedding model just to use OSII.

A semantic model may recognize related meanings. A lexical hashing method
captures shared wording. Both fit this API, but they make different promises.
Declare the actual model and its version so a researcher can tell what was
compared and rebuild derived results when the method changes.

An embedder does not decide which files to search, change source text, or split
the corpus into chunks. See [retrieval chunking](../../concepts/retrieval-chunking.md)
for Core's chunking boundary.

## Endpoint

`POST /v1/embed`

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
  "request_id": "vectors-1",
  "inputs": [
    {"id": "chunk-1", "text": "The sensor passed."},
    {"id": "chunk-2", "text": "Sensor failed."}
  ]
}
```

| Field | Type | Required / default | Meaning |
| --- | --- | --- | --- |
| `api_version` | string | No; `"v1"` | Only v1 is accepted |
| `request_id` | string | Yes | Caller-generated operation ID; echo unchanged |
| `inputs` | EmbeddingInput[] | Yes; at least one | Explicit text batch |
| `inputs[].id` | string | Yes | Identity to preserve in the response |
| `inputs[].text` | string | Yes | Exact text to represent; empty string is schema-valid |
| `inputs[].metadata` | object | No; `{}` | Explicit source/context metadata |
| `config` | object | No; `{}` | Non-secret settings validated by the method |
| `model_context` | ModelContext or null | No; `null` | Short-lived gateway access, normally supplied by Core |

There is no `expert_context` field on this request. Use unique input IDs: the
schema checks a nonempty batch but not ID uniqueness. State model text/batch
limits, truncation rules, and query/document preprocessing; never silently
drop an input.

## Response format

### Example response

This is the matching example result. Optional nulls and some default-valued
nested fields are omitted for readability; the SDK HTTP helper normally
serializes those defaults too. This is valid response JSON, not a schematic
with placeholders.

```json
{
  "api_version": "v1",
  "request_id": "vectors-1",
  "processor": {
    "name": "demo.text-lengths",
    "version": "1.0.0",
    "display_name": "Text lengths (teaching example)",
    "description": "Returns word and character counts; not semantic embeddings.",
    "kind": "embedder",
    "capabilities": {
      "output_kinds": [
        "embedding_vector"
      ]
    }
  },
  "model": "demo-word-character-counts-v1",
  "vectors": [
    {
      "id": "chunk-1",
      "vector": [
        3,
        18
      ],
      "dimensions": 2
    },
    {
      "id": "chunk-2",
      "vector": [
        2,
        14
      ],
      "dimensions": 2
    }
  ],
  "normalized": false,
  "metadata": {}
}
```

| Field | Type | Required / default | Meaning |
| --- | --- | --- | --- |
| `api_version` | string | No; `"v1"` | Protocol version |
| `request_id` | string | Yes | Unchanged request ID |
| `processor` | ProcessorDescriptor | Yes | Method identity and version |
| `model` | string | Yes | Vector representation identity |
| `vectors` | EmbeddingVector[] | Yes | One per input in request order |
| `vectors[].id` | string | Yes | Matching input identity |
| `vectors[].vector` | number[] | Yes | Vector values |
| `vectors[].dimensions` | integer | Yes; greater than 0 | Must equal vector length |
| `normalized` | boolean | No; `false` | Producer's normalization claim |
| `metadata` | object | No; `{}` | Method/provider information |

The SDK checks unique output IDs, vector lengths, and consistent dimensions.
It permits an empty `vectors` list and does not check input coverage/order,
finite values, or actual normalization. A successful batch should not be empty:
validate one finite vector for every input. Core's remote adapter checks exact
ID coverage and reorders by input ID; this does not replace producer checks.

There is no `warnings` field. Fail a batch you cannot satisfy rather than
returning a silently incomplete result. Method-specific notices can be placed
in documented `metadata`, but there is no standardized partial-success format.

Use the same representation for queries and indexed text. Equal dimensions
alone do not make models compatible. State normalization (for example, L2 unit
length) and distance metric; v1 does not specify either. Changing model,
preprocessing, or dimensions requires rebuilding affected derived vectors.

## Errors and operational behavior

These are synchronous JSON endpoints, not multipart uploads or background
job submissions. `200` returns the result, not a saved Core object.
The SDK helper returns `422` for malformed/invalid requests or a method's
`ValueError`; unhandled failures normally return `500`.
See [error examples and transport limits](index.md#errors-and-transport-limits)
for exact shapes, timeouts, authentication, and retry limits.

## Compliance checklist

- [ ] Reject duplicate input IDs and unsupported text/batch sizes.
- [ ] Echo the request ID and identify processor plus representation.
- [ ] Return exactly one finite vector per input in the same order.
- [ ] Verify positive, matching, consistent dimensions.
- [ ] Document preprocessing, model revision, metric, and normalization.
- [ ] Reject an unsatisfied batch rather than silently dropping inputs.

These are implementation obligations, not a claim that every rule is
automatically enforced by the SDK. The
[backend review](index.md#backend-review-what-is-enforced-today) separates
schema checks from remaining hardening decisions.

## A small working example

This **teaching example** returns two values: word count and character count.
It demonstrates identity, order and dimensions. It is not a semantic model
or a useful general-purpose retrieval method. No model download is needed.

Copy blocks 1–4 in order into `my_processor.py` or a Python session.

### 1. Import the contract

```python
from osii.processor_sdk import (
    Capability, Embedder, EmbeddingInput,
    EmbeddingRequest, EmbeddingResponse, EmbeddingVector,
    ProcessorDescriptor, ProcessorKind, create_processor_app,
)
```

### 2. Describe and implement your method

```python
DESCRIPTOR = ProcessorDescriptor(
    name="demo.text-lengths", version="1.0.0",
    display_name="Text lengths (teaching example)",
    description="Returns word and character counts; not semantic embeddings.",
    kind=ProcessorKind.EMBEDDER,
    capabilities=Capability(output_kinds=["embedding_vector"]),
)
```

```python
class LengthEmbedder(Embedder):
    descriptor = DESCRIPTOR

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        vectors = [
            EmbeddingVector(
                id=item.id,
                vector=[float(len(item.text.split())), float(len(item.text))],
                dimensions=2,
            )
            for item in request.inputs
        ]
        return EmbeddingResponse(
            request_id=request.request_id, processor=self.descriptor,
            model="demo-word-character-counts-v1",
            vectors=vectors, normalized=False,
        )
```

`descriptor.version` identifies the processor implementation.
`response.model` identifies the vector representation. If you change the
representation, change that identity too.

### 3. Call it directly

```python
request = EmbeddingRequest(
    request_id="vectors-1",
    inputs=[
        EmbeddingInput(id="chunk-1", text="The sensor passed."),
        EmbeddingInput(id="chunk-2", text="Sensor failed."),
    ],
)
processor = LengthEmbedder()
result = processor.embed(request)
for item in result.vectors:
    print(item.id, item.vector)
```

Output:

```text
chunk-1 [3.0, 18.0]
chunk-2 [2.0, 14.0]
```

The IDs and order are exactly the request's IDs and order. There is no
automatic indexing or persistence in this direct call.

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
remote_result = client.embed(request)
print(remote_result.model, remote_result.vectors[0].dimensions)
```

## Choose a real implementation

The guaranteed `local.hashing` service produces deterministic
384-dimensional lexical vectors without model downloads. It is explicitly
not a semantic embedding model.

The provider bridge also exposes explicitly selected Ollama and
OpenAI-compatible embedding models behind this contract. Use
[model-provider configuration](../model-providers.md) for connection setup.
A custom gateway-backed method declares
`model_requirements={"embedding": "required"}`.

Model choice belongs in configuration; source identity and persistence belong
in Core. Keeping those boundaries separate lets you compare retrieval methods
without changing the underlying evidence.

## Troubleshooting

| What you see | What to check |
| --- | --- |
| HTTP 422 on an empty batch | `inputs` must contain at least one item |
| Dimension validation error | Each declared dimension must match its vector length |
| IDs missing, reordered or duplicated | Preserve one output per input; validate the complete request/response mapping |
| Similarity makes little sense | Confirm query/index model identity; do not use this teaching example for semantic retrieval |
| Index incompatible after a model update | Rebuild vectors with the new representation rather than mixing model spaces |

Next: [enrichment](enrichment.md) for inspectable domain knowledge, or
[the overview](index.md) to compare all four boundaries.
