# OSII Processor SDK

This small Python package defines Processor API v1: typed requests, typed
responses, standard artifact shapes, descriptors, an HTTP client, and FastAPI
service helpers for extractors, synthesizers, embedders, and enrichers.

It lives inside `osii-core/` because Core owns and validates this boundary. It
remains a separate distribution (`osii-processor-sdk`) so an independently
deployed processor can depend on the contract without installing OSII's
storage, retrieval, API, or dashboard dependencies.

Copyable implementations are in [`examples/`](examples/README.md). Processor
services receive only the bounded input in a request and return typed results;
Core alone writes the canonical `.osii` store.

From the repository root:

```bash
uv run --no-project --python 3.12 --with-editable osii-core/processor-sdk --with pytest \
  python -m pytest osii-core/processor-sdk/tests
```
