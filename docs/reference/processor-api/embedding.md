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

[Run the service](index.md#run-your-processor) and open
`http://127.0.0.1:8091/docs`. Send this to `POST /v1/embed`:

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

From a Python caller:

```python
from osii.processor_sdk import ProcessorClient

client = ProcessorClient("http://127.0.0.1:8091")
remote_result = client.embed(request)
print(remote_result.model, remote_result.vectors[0].dimensions)
```

## Request reference

| Field | Required? | Meaning |
| --- | --- | --- |
| `request_id` | Yes | Caller-generated operation ID |
| `inputs` | Yes | Nonempty list of `EmbeddingInput` |
| `inputs[].id` | Yes | Identity to preserve in the response |
| `inputs[].text` | Yes | Exact text to represent |
| `inputs[].metadata` | No | Explicit context, such as source identity; defaults to `{}` |
| `config` | No | Non-secret model/method settings |
| `api_version`, `model_context` | No in Python | See the [shared contract](index.md#the-shared-contract) |

Use unique input IDs. The request model checks that the list is nonempty;
it does not enforce uniqueness, so validate it in a production method.
If a model has a text or batch limit, report that limit clearly rather than
silently dropping an input.

## Response reference

| Field | Meaning |
| --- | --- |
| `request_id`, `processor`, `api_version` | Unchanged request ID, your descriptor, and `"v1"` |
| `model` | Required identity of the vector representation |
| `vectors` | One `EmbeddingVector` per input, in the same order |
| `vectors[].id` | Matching input ID |
| `vectors[].vector` | Numeric list |
| `vectors[].dimensions` | Positive integer equal to the vector's length |
| `normalized` | Whether your output is normalized; defaults to `false` |
| `metadata` | Optional method/provider information |

All output IDs must be unique and all vectors must have the same dimension.
The SDK checks those properties. It does not check that the response covers
the request in order, that numbers are finite, or that the claimed normalization
is correct. Production methods and direct callers should test those invariants.
There is no `warnings` field on `EmbeddingResponse`.

Use the same representation for queries and indexed text. Equal dimensions
alone do not make two models compatible. Changing the model, preprocessing
or dimensions requires rebuilding affected derived vectors/indexes.

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
