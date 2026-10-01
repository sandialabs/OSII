# OSII documentation

OSII turns local files into grounded, inspectable information that people can
browse, search, enrich, and use through AI agents. Start with the path that
matches what you want to do.

## Start here

- Read the repository README included with your checkout for the first-run path.
- [Choose a deployment or release runbook](operations/runbooks.md)
- [Run the corporate pilot bundle](operations/publishing-images.md)
- [Use a shared drive or Samba share](operations/shared-drives.md)
- [Follow the friendly Python walkthrough](tutorials/python-demonstrations.md)
- [Process one file through the CLI](tutorials/single-file.md)
- [Demonstrate tabular datasets](tutorials/tabular-datasets.md)

These pages are the normal entry points. The remaining documentation is
reference material: read it when you need to understand, extend, or operate a
specific boundary rather than from top to bottom.

After starting OSII, the dashboard's **Setup** page lists every extractor,
synthesizer, embedder, and enricher; configures extension-based extraction
routes and fallbacks; connects optional model providers; starts optional Tika
or Tesseract capabilities; and reaches advanced processor diagnostics.

## The four processor APIs

**Start with the [Python and HTTP guide](reference/processor-api/index.md).**
Each page below explains one responsibility, provides a working Python example,
and documents its request, response and service endpoint.

| Building block | What you learn |
| --- | --- |
| [Extractor](reference/processor-api/extraction.md) | Read source bytes into grounded text |
| [Synthesizer](reference/processor-api/synthesis.md) | Explain supplied evidence with citations |
| [Embedder](reference/processor-api/embedding.md) | Map identified text to vectors |
| [Enricher](reference/processor-api/enrichment.md) | Add typed tables, graphs, entities or a cited wiki |

These are the public `osii.processor_sdk` interfaces included in the `osii`
Python package. You can call your implementation directly before deploying it
as a service. Core handles storing the results when invoked through its workflows.

## Understand OSII

- [Architecture and component boundaries](concepts/architecture.md)
- [Extraction architecture](concepts/extraction.md)
- [Synthesis architecture](concepts/synthesis.md)
- [OSII store structure](reference/osii-store.md)

## Extend OSII

**New processor authors should begin here.**

1. [Choose a processor kind](extending/index.md#choose-a-processor-kind).
2. [Build the hello table enricher](extending/hello-enricher.md).
3. [Follow the processor development rules](extending/processor-development.md).
4. [Implement the Processor API v1 contract](reference/processor-api/index.md).
5. [Return a standard dashboard and agent artifact](reference/processor-api/standard-artifacts.md).

OSII extension services are ordinary Python HTTP containers. A subject-matter
expert owns the domain logic; the OSII SDK supplies validated request and
response models plus the FastAPI endpoints.

Core commit adapters validate remote extraction, synthesis, embedding, and
enrichment responses. Processor services return typed results and never write
the `.osii` store directly.

## Operate offline

- [Local and intermittently connected operation](operations/local-first.md)
- [Shared drives and Samba](operations/shared-drives.md)
- [Guaranteed container-free processor services](operations/local-processors.md)
- [Extractor routing](reference/extractor-routing.md)
- [Export components for separate repositories](operations/component-export.md)
- [Publish the consolidated images to Quay](operations/publishing-images.md)
- [Deploy Toolbox OCR, table, and embedding images](operations/publishing-images.md)
- [Sensitive data, OSII package transfer, and deletion](operations/sensitive-data.md)

## API and file-format reference

- [REST API overview](reference/api/index.md)
- [API resource model](reference/api/resource-model.md)
- [Search semantics](reference/api/search-semantics.md)
- [Keyword suggestions and example enrichments](tutorials/example-enrichments.md)
- [API compatibility](reference/api/compatibility.md)
- [Processor API v1](reference/processor-api/index.md)
- [Model-provider capabilities](reference/model-providers.md)
- [Catalog and flat-file browsing](reference/catalog.md)
- [Collection file format](reference/collection-file-format.md)
- [CLI cheat sheet](reference/cli.md)

## Contribute

- [Contributor guide](contributing/developer-guide.md)
- Run `mkdocs serve` after installing `docs/requirements.txt` to preview these
  pages locally.
