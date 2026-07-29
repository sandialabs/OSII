# Extend OSII

An OSII processor is a small HTTP service that performs one specialized task.
It receives a self-contained, validated request and returns grounded text or a
standard artifact. It never writes directly to the OSII store.

## Choose a processor kind

| You need to… | Kind | Typical input | Output |
|---|---|---|---|
| Recover the canonical text or source structure | **Extractor** | Source bytes and metadata | Text segments and source-derived artifacts |
| Explain or summarize existing grounded text | **Synthesizer** | An object, folder, collection, or root scope | Grounded Markdown and citations |
| Convert identified text into vectors | **Embedder** | Ordered IDs and text | Vectors in the same order |
| Add domain-specific structured knowledge | **Enricher** | Existing text and scope metadata | Tables, graphs, entities, or wiki Markdown |

Use an extractor when your parser defines what the source fundamentally says.
Use an enricher when it adds a specialist interpretation alongside canonical
text. For example, recovering text from a laboratory PDF is extraction;
turning that recovered text into an experiment-results table is enrichment.

## The extension path

1. Start with the [hello table enricher](hello-enricher.md).
2. Copy the closest implementation from
   `packages/osii-processor-sdk/examples/`.
3. Give the processor a stable descriptor name and semantic version.
4. Implement the one method for its processor kind.
5. Test representative, redistributable examples locally.
6. Package the service in a container.
7. Register its base URL under **Admin → Processors**.
8. Use **Health** to test liveness and **Test** to validate the v1 contract.
9. Run it against an ingested file and inspect the result in the dashboard.

## What OSII handles for you

- versioned and strict request and response models;
- `/health` and `/v1/descriptor`;
- the kind-specific operation endpoint;
- canonical persistence and provenance;
- dashboard and agent views for standard artifacts.

Read the [processor development rules](processor-development.md) before
building a production processor, then use the
[Processor API reference](../reference/processor-api/index.md) for exact
payloads.

## Current limitation

Remote enrichers are the first fully integrated extension type. External
extractors, synthesizers, and embedders can implement, expose, register, and
contract-test the v1 API today, but OSII does not yet commit their returned
results into the canonical store. Keep those services experimental until the
corresponding core adapters land.

