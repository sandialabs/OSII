# OSII documentation

OSII turns local files into grounded, inspectable information that people can
browse, search, enrich, and use through AI agents. Start with the path that
matches what you want to do.

## Install and use OSII

- [Get started from the repository README](https://github.com/heidikmkv/osii#getting-started--no-development-experience-required)
- [Process one file end to end](tutorials/single-file.md)
- [Use the command line](reference/cli.md)
- [Follow the Python demonstrations](tutorials/python-demonstrations.md)

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

> [!NOTE]
> Remote enrichers execute end to end and their standard artifacts appear in
> the dashboard and agent APIs. External extractors, synthesizers, and
> embedders have stable v1 wire contracts and can be registered and tested,
> but their core-side commit adapters are still being completed.

## Operate offline

- [Local and intermittently connected operation](operations/local-first.md)
- [Extractor routing](reference/extractor-routing.md)
- [Export components for separate repositories](operations/component-export.md)

## API and file-format reference

- [REST API overview](reference/api/index.md)
- [API resource model](reference/api/resource-model.md)
- [Search semantics](reference/api/search-semantics.md)
- [API compatibility](reference/api/compatibility.md)
- [Processor API v1](reference/processor-api/index.md)
- [Model-provider capabilities](reference/model-providers.md)
- [Collection file format](reference/collection-file-format.md)

## Contribute

- [Contributor guide](contributing/developer-guide.md)
- Run `mkdocs serve` after installing `docs/requirements.txt` to preview these
  pages locally.
