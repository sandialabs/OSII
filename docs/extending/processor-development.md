# Develop an OSII processor

Start with the [hello table enricher](hello-enricher.md), then copy the closest
small implementation from `osii-core/processor-sdk/examples/`.

The extension API is included in OSII. From the monorepo root, install it with
`python -m pip install ./osii-core` in your Python environment. After publication
to your package registry, use `python -m pip install osii`. Import from
`osii.processor_sdk`; existing `osii_processor_sdk` imports remain compatible.

## Choose the boundary first

| Kind | Responsibility | Must not do |
|---|---|---|
| Extractor | Convert source bytes into canonical text segments and source-derived artifacts | Interpret or summarize the extracted corpus |
| Synthesizer | Produce grounded Markdown over existing text | Reparse original source files |
| Embedder | Map identified text inputs to vectors in order | Change text or canonical persistence |
| Enricher | Produce structured derived artifacts over existing text | Write directly into `.osii` |

A specialist table parser is usually an extractor when its output defines the
document's canonical text. It is an enricher when it adds structured table
data alongside text that has already been extracted.

## Implement the SDK interface

Each service subclasses exactly one SDK interface and declares one descriptor:

```python
from osii.processor_sdk import (
    Enricher,
    EnrichmentRequest,
    EnrichmentResponse,
    ProcessorDescriptor,
    ProcessorKind,
    create_processor_app,
)


class MyProcessor(Enricher):
    descriptor = ProcessorDescriptor(
        name="my-team.my-processor",
        version="1.0.0",
        display_name="My Processor",
        description="Describe the domain result.",
        kind=ProcessorKind.ENRICHER,
        config_schema={
            "type": "object",
            "properties": {
                "instructions": {
                    "type": "string",
                    "title": "Analysis prompt",
                    "description": "Domain guidance applied to the source text.",
                    "default": "Extract only facts grounded in the supplied source.",
                    "format": "textarea",
                },
                "temperature": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 2,
                    "default": 0.2,
                },
            },
            "additionalProperties": False,
        },
    )

    def enrich(self, request: EnrichmentRequest) -> EnrichmentResponse:
        ...


app = create_processor_app(MyProcessor())
```

The helper exposes `/health`, `/v1/descriptor`, and the kind-specific operation
endpoint. See the [Processor API reference](../reference/processor-api/index.md)
for exact payloads.

## Use a language model without learning an OSII client

Declare the capability in the descriptor and accept a normal OpenAI client in
the handler. Install the optional dependency with `pip install 'osii[openai]'`.

```python
from openai import OpenAI
from osii.processor_sdk import (
    EnrichmentRequest, EnrichmentResponse, ProcessorDescriptor,
    ProcessorKind, create_openai_processor_app,
)

DESCRIPTOR = ProcessorDescriptor(
    name="my-team.grounded-wiki",
    version="1.0.0",
    display_name="Grounded Wiki",
    description="Creates a cited wiki from extracted text.",
    kind=ProcessorKind.ENRICHER,
    model_requirements={"chat": "required"},
)

def create_wiki(
    request: EnrichmentRequest, *, client: OpenAI, model: str
) -> EnrichmentResponse:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Summarize only the supplied source."}],
    )
    # Validate and return standard artifacts here.
    ...

app = create_openai_processor_app(
    descriptor=DESCRIPTOR,
    handler=create_wiki,
    model_capability="chat",
)
```

Test that exact function directly with any OpenAI-compatible endpoint:

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url=os.environ["OPENAI_BASE_URL"],
    api_key=os.environ["OPENAI_API_KEY"],
)
result = create_wiki(request, client=client, model=os.environ["OPENAI_MODEL"])
```

When Core invokes it, the SDK constructs the same client against the internal
Model Gateway using a short-lived token. Self-contained processors use
`create_processor_app` and install no OpenAI dependency.

## Expose settings without dashboard code

Setup renders `config_schema` as a generic settings form under **Advanced &
diagnostics**. String and multiline
prompt fields, numbers, integers, Booleans, and enums require no custom
frontend implementation. Saved non-secret defaults live in
`.osii/state/processor_settings.json`; explicit values in an API request take
precedence. The core passes the resulting object unchanged as `request.config`.

Keep deployment settings such as URLs and credential environment-variable
names in the provider/endpoint configuration. Never declare API keys or other
secrets as processor settings. A custom dashboard component is only necessary
for richer interactions that JSON Schema cannot describe, such as drawing a
page region or visually mapping table columns.

## Production requirements

- Use a stable, namespaced processor name and semantic version.
- Return the request ID unchanged.
- Validate all configuration with JSON Schema.
- Bound input size, runtime, memory, and output size.
- Produce deterministic results for identical input where practical.
- Include the narrowest provenance that the processor can defend.
- Return a [standard artifact](../reference/processor-api/standard-artifacts.md)
  when the result should work in the dashboard and agent interfaces.
- Never mount a writable OSII store into the processor container.
- Test representative, redistributable fixtures and malformed requests.
- Bundle all required dependencies and model assets for air-gapped operation.

## Register and verify

Use **Setup → Advanced & diagnostics → Register running processor** and paste
only the service base URL. OSII reads the descriptor and shows its kind,
scopes, outputs, and model requirements. Choose a model connection when one is
required. **Health** verifies liveness and **Descriptor** checks the contract.

External extractors, synthesizers, embedders, and enrichers use the same
descriptor, settings, request, and core-owned commit flow.
