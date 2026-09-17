# OSII Processor SDK

The `osii.processor_sdk` module defines Processor API v1: typed requests, typed
responses, standard artifact shapes, descriptors, an HTTP client, and FastAPI
service helpers for extractors, synthesizers, embedders, and enrichers.

It is included in the single `osii` distribution. Install OSII once to use
both Core and its processor contracts. The implementation lives in
`osii-core/osii/processor_sdk/`; this directory holds examples and tests.
Existing `osii_processor_sdk` imports remain supported through a compatibility
module included with OSII. There is no separate SDK distribution to install.

From the repository root, install with `python -m pip install ./osii-core`.
After OSII is published to your package registry, use `python -m pip install osii`.
Processor environments install the same dependencies as Core; no extras are
required. Installing code does not start Core or give a processor store access.

Copyable implementations are in [`examples/`](examples/README.md). Processor
services receive only the bounded input in a request and return typed results;
Core alone writes the canonical `.osii` store.

From the repository root:

```bash
uv run --no-project --python 3.12 --with-editable osii-core --with pytest \
  python -m pytest osii-core/processor-sdk/tests
```
