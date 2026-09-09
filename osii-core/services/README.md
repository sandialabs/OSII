# Core-owned local services

These small service packages provide OSII's guaranteed local processor hosts:
native text extraction, source-excerpt synthesis, lexical compatibility
embeddings, statistics/keywords enrichment, and HTTP adapters for configured
model providers.

They are grouped inside `osii-core/` because the standard installation starts
and tests them with Core. Each still has its own package, descriptor, API,
tests, port, and process boundary, so it can be run in its own container or
exported into a separate repository. None writes `.osii`; Core sends bounded
requests and commits validated results.

Optional OCR, dataset-specific, experimental, and heavyweight model services
belong in [`../../osii-toolbox/`](../../osii-toolbox/README.md) instead.
