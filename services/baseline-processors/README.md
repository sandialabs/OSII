# OSII baseline-processors image

This packaging directory consolidates five small, model-free or HTTP-only
services into one publishable image. Each deployment still runs one capability
per container so it can be scaled, replaced, or exported independently.

Available commands are `extractor`, `synthesizer`, `embedder`, `enricher`, and
`model-bridge`. For example:

```bash
podman run --rm -p 8092:8092 quay.io/your-org/osii-baseline-processors:0.1.0 extractor
podman run --rm -p 8085:8085 quay.io/your-org/osii-baseline-processors:0.1.0 embedder
```

The image contains no model weights, Hugging Face client, Ollama runtime, or
corporate dependency. The model bridge makes HTTP calls only when an optional
provider capability is selected.

The Processor API v1 contract is included in every image at
`/workspace/PROCESSOR_API.md`; each running service also exposes its exact
OpenAPI schema at `/docs`.
