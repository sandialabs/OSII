# The four processor APIs

OSII's four processor building blocks are **extractors, synthesizers,
embedders, and enrichers**. Each answers a different question about your
documents. You can use their Python interfaces directly, or expose the same
code as a service that Core calls.

Start with the question you want to answer:

| Your question | Processor | Receives | Returns |
| --- | --- | --- | --- |
| What does this source contain? | [Extractor](extraction.md) | One document's bytes | Grounded text segments and optional source artifacts |
| What does this evidence tell us? | [Synthesizer](synthesis.md) | Text from an explicit scope | Markdown and citations |
| How can we compare these texts numerically? | [Embedder](embedding.md) | Identified text inputs | A vector for each input, in order |
| What useful knowledge can we add? | [Enricher](enrichment.md) | Text from an explicit scope | Tables, graphs, entities, or a cited wiki |

Each linked page has a complete, small Python example, an input/output
reference, a service endpoint, and troubleshooting. None of the teaching
examples needs a model, a running Core, or containers.

## Why four separate building blocks?

Reading a document, summarizing its evidence, representing text numerically,
and adding specialist knowledge are different responsibilities. Keeping them
separate lets you improve one method without rewriting the rest of OSII.

For example, an OCR extractor reads a scanned report. A synthesizer prepares a
cited overview. An enricher turns reported measurements into a comparison
table. An embedder can support vector retrieval when that method is useful.
They do not all have to run, and they do not form a mandatory four-step pipeline.

The useful boundary is **explicit input → understandable computation → typed
output**. Core chooses the source or scope, supplies the evidence, validates
the response, and persists it. A processor owns its domain method; it does
not choose an unseen corpus or write the canonical `.osii` store.

This is also the basis for agent workflows: an agent can request a bounded
operation and inspect its result through Core's APIs. The same standard
artifacts are available to the dashboard and to agents. Model output remains
derived information, with source evidence that a human can check.

## Start in Python

The public interface is `osii.processor_sdk`, included in the single
`osii` Python package. There is no separate SDK package to install.

In an existing Python environment, install from your checkout's root:

```sh
python -m pip install ./osii-core
```

When available in your configured package registry, `python -m pip install osii`
installs the same public interfaces. Installing the package does not start
any services.

Open one of the four pages and copy its numbered Python blocks in order into
`my_processor.py`. The first blocks define the processor; the next constructs
a request and calls it directly. That is ordinary Python:

```python
# Each processor page supplies the class and request.
result = processor.extract(request)       # Extractor
# result = processor.synthesize(request)  # Synthesizer
# result = processor.embed(request)       # Embedder
# result = processor.enrich(request)      # Enricher
```

A direct call returns a typed result; it does **not** ingest a document or
save an artifact into your OSII library. Use Core's workflows for that
([Core REST API](../api/index.md), or the dashboard). Keep the computation
testable before adding a transport or deployment.

## Run your processor

Each page ends with `app = create_processor_app(...)`. With its Python blocks
saved as `my_processor.py`, run from the folder containing that file:

```sh
python -m uvicorn my_processor:app --host 127.0.0.1 --port 8091
```

Mac, Windows, and Linux use the same command. If you prefer `uv`, run this
from the OSII root with the example file saved there:

```sh
uv run --no-project --python 3.12 --with-editable osii-core python -m uvicorn my_processor:app --host 127.0.0.1 --port 8091
```

Use one example at a time on that port. Stop with Ctrl+C.
Open **http://127.0.0.1:8091/docs** in your browser: the SDK's FastAPI helper
provides the exact schema and a **Try it out** button. Paste the JSON request
from the relevant page to exercise the endpoint.

| Endpoint | What you can inspect |
| --- | --- |
| `GET /health` | Service liveness: `{"status": "ok"}` |
| `GET /v1/descriptor` | Identity, processor kind, capabilities, settings and model requirements |
| `GET /docs` | Interactive API documentation |
| `GET /openapi.json` | Machine-readable schema |
| `POST /v1/extract`, `/v1/synthesize`, `/v1/embed`, or `/v1/enrich` | The one operation matching the processor kind |

These are **processor** endpoints. Core's own API normally runs on port
8511; these four operation routes are not Core REST routes. A larger host can
mount several processor apps at separate base paths.

Once it works locally, register the running service under **Setup → Advanced &
diagnostics → Register running processor**. Enter its base URL, not the
operation path. When Core runs in a container, host loopback is the container
itself: use a reachable container service name or `host.containers.internal`
for a processor on the workstation. A host-only server bound to
`127.0.0.1` may need an appropriate network binding and firewall policy before
a container can reach it. See [processor development](../../extending/processor-development.md)
for registration and deployment details.

## The shared contract

All request and response envelopes carry `api_version="v1"` and a
`request_id`. Python supplies the API-version default for you. Return the
request ID unchanged and include your `ProcessorDescriptor` in the response.

| Shared field | Meaning |
| --- | --- |
| `request_id` | Caller-chosen identifier for this operation |
| `config` | Non-secret method settings; defaults to an empty dictionary |
| `expert_context` | Optional human guidance on extraction, synthesis and enrichment |
| `model_context` | Optional short-lived model-gateway access; normally supplied by Core |
| `processor` | Response descriptor identifying the method and its version |

SDK models reject unknown top-level fields. Dictionaries such as `metadata`,
`config`, and `source_origin` deliberately hold method-specific information.
`expert_context` is guidance, not source evidence or a citation. Core resolves
saved context for a requested scope; a direct SDK call supplies only what
you put in the request.

A descriptor needs `name`, `version`, `display_name`, `description`, and
`kind`. Give it a stable lowercase namespaced name, such as
`my-team.lab-measurements`. Declare supported file types, scopes and output
kinds through `Capability`; these declarations describe suitability, but your
method must still validate its inputs.

`config_schema` describes a non-secret settings form using JSON Schema.
The service helper does not automatically enforce that schema on the
contents of `request.config`: validate method settings in your implementation.
The examples omit tunable settings so you can see the contract first.

## Call an existing service

`ProcessorClient(base_url, timeout=120.0)` wraps HTTP with the same typed
requests and responses. Each processor page gives the matching client call.
It reads the descriptor through `client.descriptor()`.

| Situation | What happens |
| --- | --- |
| Malformed request JSON or invalid SDK fields | FastAPI returns HTTP 422 |
| Your class-based processor raises `ValueError` | `create_processor_app` returns HTTP 422 with the error detail |
| HTTP/network error or invalid JSON response | The client raises `ProcessorClientError` |
| Response JSON violates the typed contract | Pydantic raises `ValidationError` |
| An unexpected implementation error | Treat as a server failure; inspect service logs |

The client validates response shape. It does not automatically check every
relationship to the original request or persist the result; for direct callers,
check the echoed ID and operation-specific invariants. Core's adapters add
request/response checks when committing results. A green `/health` indicates
liveness, not proof of correct output or available model access.

## Add a model when your method needs one

The four boundaries stay the same whether your implementation uses rules,
native libraries, a local model, or an approved endpoint. Declare
`model_requirements={"chat": "required"}` or
`{"embedding": "required"}` in the descriptor for a model-backed method.

Core can then pass a short-lived `ModelContext` pointing at its
OpenAI-compatible gateway, without passing the upstream provider key.
For the ready-made gateway adapter, see
[model-backed Python handlers](../../extending/processor-development.md#use-a-language-model-without-learning-an-osii-client).
You do not need this adapter or its optional dependency for the examples here.

## Where to go next

- [Extractor](extraction.md): recover grounded text.
- [Synthesizer](synthesis.md): produce cited Markdown.
- [Embedder](embedding.md): return identified vectors.
- [Enricher](enrichment.md): return knowledge people and agents can inspect.
- [Canonical output boundaries](canonical-outputs.md) and
  [standard artifact schemas](standard-artifacts.md): detailed formats.
- [Processor development](../../extending/processor-development.md): production settings,
  model access, registration and packaging.
