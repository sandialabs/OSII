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
    )

    def enrich(self, request: EnrichmentRequest) -> EnrichmentResponse:
        ...


app = create_processor_app(MyProcessor())
```

The helper exposes `/health`, `/v1/descriptor`, and the kind-specific operation
endpoint. See the [Processor API reference](../reference/processor-api/index.md)
for exact payloads.

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

Register the service base URL under **Admin → Processors**. **Health** verifies
liveness. **Test** reads the descriptor, checks that its kind matches the
registration, and sends a small contract-valid operation request.

Remote enrichers currently execute end to end. External extractors,
synthesizers, and embedders can be registered and contract-tested, but their
core commit adapters are still incomplete.

