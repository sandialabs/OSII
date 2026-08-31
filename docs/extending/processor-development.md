# Develop an OSII processor

Start with the [hello table enricher](hello-enricher.md), then copy the closest
small implementation from `packages/osii-processor-sdk/examples/`.

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
from osii_processor_sdk import (
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

Register the service base URL under **Setup → Advanced & diagnostics → Custom Processor API services**. **Health** verifies
liveness. **Test** reads the descriptor, checks that its kind matches the
registration, and sends a small contract-valid operation request.

External extractors, synthesizers, embedders, and enrichers use the same
descriptor, settings, request, and core-owned commit flow.
