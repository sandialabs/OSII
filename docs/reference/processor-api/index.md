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

Each linked Markdown file is one operation's specification: endpoint, paired
JSON examples, typed fields/defaults, edge cases, errors, and a compliance
checklist first; a small working Python implementation follows. You can review
the contract without assembling a tutorial. None of the teaching examples
needs a model, a running Core, or containers.

For shared envelopes and deployment behavior, read
[the shared contract](#the-shared-contract) and
[errors and transport limits](#errors-and-transport-limits).
To assess backend stability, start with
[what is enforced today](#backend-review-what-is-enforced-today).

## Why four separate building blocks?

Reading a document, summarizing its evidence, representing text numerically,
and adding specialist knowledge are different responsibilities. Keeping them
separate lets you improve one method without rewriting the rest of OSII.

For example, an OCR extractor reads a scanned report. A synthesizer prepares a
cited overview. An enricher turns reported measurements into a comparison
table. An embedder can support vector retrieval when that method is useful.
They do not all have to run, and they do not form a mandatory four-step pipeline.

The useful boundary is **explicit input → understandable computation → typed
output**. Core chooses the source or scope, supplies the evidence, integrates
the response, and owns persistence. A processor owns its domain method; it does
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

All operation requests and responses carry `api_version` (optional, default
`"v1"`) and required string `request_id`. These defaults apply to HTTP as
well as Python. Return the ID unchanged. It is a correlation identifier:
the SDK does not make repeated IDs idempotent or deduplicate work.

All SDK model objects reject unknown fields, including nested typed objects.
This is not Pydantic strict-type mode: supported coercions can still occur.
Free dictionaries (`config`, `metadata`, `source_origin`, properties) accept
method-specific content. Required string fields generally have no nonempty
constraint; the descriptor name has the pattern shown below.

### ProcessorDescriptor

Every response contains this object; `GET /v1/descriptor` returns it directly.

| Field | Type | Required / default | Meaning |
| --- | --- | --- | --- |
| `api_version` | string | No; `"v1"` | Only v1 |
| `name` | string | Yes | Stable ID matching `^[a-z0-9][a-z0-9_.-]*$` |
| `version` | string | Yes | Implementation version; semver is a convention, not schema-enforced |
| `display_name` | string | Yes | Human-readable method name |
| `description` | string | Yes | What it does, including experimental/model-backed limits |
| `kind` | string | Yes | `extractor`, `synthesizer`, `embedder`, or `enricher` |
| `capabilities` | Capability | No; empty lists | Advertised input/scope/output suitability |
| `config_schema` | object | No; `{}` | JSON Schema for non-secret settings |
| `model_requirements` | object | No; `{}` | Keys `chat`/`embedding`; values `required`/`optional` |

`Capability` has `media_types: string[]`, `file_extensions: string[]`,
`scope_types: ("object" | "folder" | "collection" | "root")[]`, and
`output_kinds: string[]`, all defaulting to `[]`. Empty lists mean no
declaration, not proof of universal support. The helper checks the class's
descriptor kind at startup; capabilities are descriptive, not enforced input
filters.

`config_schema` describes a settings form. The helper does not enforce it
against `request.config`, insert its defaults, or validate the schema itself.
Validate settings in the method. Human `expert_context` is optional guidance
on extraction, synthesis, and enrichment; it is not evidence, and embedding
does not have that field.

### DocumentInput and ScopeInput

The operation pages list these nested fields in full. `DocumentInput`
requires only a filename: bytes, text, and segments are independent optional
representations, not a one-of payload. State which your method consumes and
how it handles absent or conflicting representations. `ScopeInput` requires
a scope type and ID; its documents default to an empty list. A scope is not
permission to discover additional sources.

### ModelContext

| Field | Type | Required / default | Meaning |
| --- | --- | --- | --- |
| `gateway_url` | string | Yes | Core's short-lived OpenAI-compatible gateway URL |
| `token` | string | Yes | Ephemeral access credential; do not log or persist |
| `bindings` | object | No; `{}` | `chat`/`embedding` keys mapped to gateway model IDs |

This is normally supplied by Core, not a user's upstream provider key.
The SDK schema does not validate URL safety or token expiry. Processors must
not retain it in artifacts, provenance, logs, or configuration.

### Artifact envelope

Extraction may return source-derived artifacts. Enrichment must return
standard derived artifacts. Both use this envelope:

| Field | Type | Required / default | Meaning |
| --- | --- | --- | --- |
| `id` | string | Yes | Processor-local artifact identity |
| `kind` | string | Yes | Descriptive method label, not the format discriminator |
| `media_type` | string | Yes | Payload MIME type |
| `data_base64` | string or null | No; `null` | Binary payload encoded as base64 |
| `text` | string or null | No; `null` | Text payload |
| `json_data` | JSON value or null | No; `null` | Arbitrary source-derived JSON payload |
| `standard_data` | StandardArtifactData or null | No; `null` | One of the four [standard formats](standard-artifacts.md) |
| `source_origin` | object | No; `{}` | Source location |
| `metadata` | object | No; `{}` | Non-secret method/payload details |

Exactly one payload must be non-null. Empty text/empty objects count as
payloads; `json_data: null` does not. Enrichment additionally requires
`standard_data` and unique artifact IDs. Extraction does not check artifact
ID uniqueness. The schema does not validate encoded bytes or MIME/payload
agreement. Core's remote extraction path persists artifact payload and
`source_origin`, but does not forward artifact `metadata` to its persistence
call. Verify the stored representation if you rely on optional envelope fields.

### Provenance and source locations

`ProvenanceRef` is fully listed on the [synthesizer page](synthesis.md#provenanceref)
and reused by all standard artifacts. It has optional source/segment IDs,
one-based page, nonnegative character offsets, and free `source_origin`.
Use `[char_start, char_end)` against the exact supplied text. None of those
fields is required by the schema, so a syntactically valid reference may still
be ungrounded.

`TextSegment.source_origin` is also free-form, not a typed geometry or quality
standard. The [extractor OCR section](extraction.md#ocr-confidence-and-geometry)
documents the existing Tesseract/OpenCV convention and its limits.

## Call an existing service

`ProcessorClient(base_url, timeout=120.0)` wraps synchronous HTTP with the
same typed models. Use `client.descriptor()` to inspect a running method,
then the matching operation. It validates response shape, not the semantic
relationship to the request; check echoed IDs, evidence, and completeness.

## Errors and transport limits

The following describes the class-based `create_processor_app` helper.
A custom server must document any differences.

| HTTP status | Meaning | Response |
| --- | --- | --- |
| `200` | Operation returned a schema-valid result | Operation-specific JSON |
| `422` | Request parsing/schema failure | `{"detail": [validation errors]}` |
| `422` | Processor raised `ValueError` | `{"detail": "actionable explanation"}` |
| `500` | Unhandled error or invalid returned response | No stable JSON error envelope is guaranteed |
| `404` / `405` | Wrong route / method | Framework error; check the processor's base URL |

For example, the UTF-8 teaching extractor rejects an absent payload with:

```json
{"detail": "Supply the source bytes in document.content_base64."}
```

A missing `request_id` produces a validation error shaped like:

```json
{
  "detail": [{
    "type": "missing",
    "loc": ["body", "request_id"],
    "msg": "Field required",
    "input": {"document": {"filename": "sensor.txt"}}
  }]
}
```

Validation details can echo input, potentially including text or credentials.
Treat diagnostic responses and logs as sensitive. A Pydantic validation
failure raised while constructing a response inside the method is also a
`ValueError`, so the helper may return `422` for that producer bug.
Response validation after the method returns normally becomes `500`.
Do not copy another API's `{"error": "..."}` envelope here.

| Concern | Current v1 behavior |
| --- | --- |
| Encoding | Inline JSON; binary bytes use base64, not multipart/path references |
| Execution | Synchronous operation; no job polling, streaming, or cancellation contract |
| Timeout | Client default 120 seconds; no SDK server-side operation deadline |
| Retries | Client has no built-in retry; a timeout does not prove server work stopped |
| Idempotency | No deduplication guarantee; repeated calls can compute again |
| Limits | No SDK byte, document-count, batch-size, or concurrency ceiling |
| Authentication | The helper has no built-in processor-service authentication or TLS |
| Model access | `model_context.token` authorizes model-gateway access, not incoming processor requests |
| Health | `/health` proves liveness only, not model readiness or output correctness |

Use an approved network boundary, TLS/authentication at the deployment edge,
and explicit resource limits before exposing a processor beyond trusted local
use. These are deployment obligations, not features that the helper silently
provides. The OpenAI handler adapter differs from the class helper on some
error paths: required missing bindings return `422`, but its optional
no-model branch calls the handler without the same `ValueError` wrapper.

The client wraps HTTP/network errors and invalid JSON as
`ProcessorClientError`; invalid response fields raise Pydantic
`ValidationError`. It has no automatic persistence.

## Backend review: what is enforced today

This is a source-checked review, not a declaration that the backend is frozen.
“Should” in a checklist is an implementation obligation; it is not necessarily
an automatic validator.

| Boundary | Enforced today | Still requires review or hardening |
| --- | --- | --- |
| SDK envelopes | v1 literal, typed fields, unknown fields rejected | Nonempty IDs/version policy, descriptor identity/kind agreement with the operation, semantic compatibility, resource ceilings |
| Extraction | Unique segment IDs | Geometry/quality conventions, related IDs, artifact ID uniqueness; Core rejects empty segments |
| Synthesis | Markdown shape, citation field types/minimum offsets | Citation/source membership, span bounds, claim-to-citation mapping and support |
| Embedding | Unique output IDs, consistent positive dimensions matching lengths | Input ID uniqueness, finite values, correct normalization/model space; Core adds ID coverage and reordering |
| Enrichment | SDK requires unique IDs, nonempty artifacts, typed standard data | Core's remote enricher uses raw JSON/legacy fallbacks, not full `EnrichmentResponse` validation or echoed-ID checks; response warnings are not propagated in its result |
| Tables | Unique column keys; populated row provenance matches row count | Row keys and values are not validated against column types; real provenance |
| Graphs/entities | Unique graph/entity IDs; edges reference existing nodes | Correct relationships, source membership, confidence semantics |
| Quality | Free metadata can carry method-specific scores | No universal typed confidence, quality policy, or calibration guarantee |
| Transport | Synchronous helper, typed requests/responses, liveness | Uniform error policy, authentication, deadlines, limits, retry/idempotency policy |

Source of truth: `osii-core/osii/processor_sdk/models.py`,
`service.py`, `client.py`, and Core integration in
`osii-core/osii/processors/remote.py`. A running service's
`/openapi.json` describes its deployed schema; it cannot prove semantic
correctness or that it matches a different release's code.

### Decisions before calling the contract stable

These are review recommendations, **not implemented changes**:

1. Align Core's remote enricher with the typed v1 envelope and request-ID
   checks; decide when legacy fallback support ends.
2. Define an optional OCR quality/location convention with score method,
   granularity, missing/unknown values, and coordinate frame. Preserve old
   stored output; missing confidence must not become “certain.”
3. Define completeness rules and limits for all four operations, including
   empty extraction/embedding and partial results.
4. Add semantic checks for finite vectors, source membership, and character
   spans. Decide whether claim-level citation links need a future contract.
5. Agree on compatibility/version policy and deployment auth, timeout, retry,
   and error behavior before exposing external processors.

Do not add a new top-level `confidence` field casually: current v1 models
reject unknown fields, so typed schema additions require a compatibility
decision. Documented optional keys inside free metadata can be introduced
without that schema change, but consumers still need agreed semantics.

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
